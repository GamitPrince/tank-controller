/*
 * ztest suite for the status-only level switch reads (S-022, P1-05).
 *
 * The spec's test plan asks for both states, the transition and a stuck input
 * on native_sim with simulated optocoupler inputs. Every case below is driven
 * from the generated contract table, so the ids, channel numbers, contact
 * senses and debounce figures come from interfaces/signals-v1.yaml and are
 * never written into this file. Each behaviour test runs for every switch the
 * signal list gives this story.
 *
 * "Stuck" is covered in both of its forms: a channel held in the asserted
 * state, which must be reported as asserted rather than smoothed away, and a
 * channel that never settles or stops being sampled, which must stop being
 * reported as live.
 */

#include <zephyr/ztest.h>

#include <errno.h>

#include "level_switch.h"

/* An id below the signal list's 1000-block floor cannot name a real signal. */
#define ID_THAT_CANNOT_EXIST 0U

/* Enough scans to prove a state keeps being reported, without being slow. */
#define SCANS_PER_HOLD 20U

/* Raw input level that means `asserted` on a channel with this contact sense. */
static bool raw_input_for(const struct tank_level_switch_config *config, bool asserted)
{
	const bool energised_means_asserted = (config->sense == TANK_CONTACT_NORMALLY_OPEN);

	return energised_means_asserted ? asserted : !asserted;
}

/* Sample one steady input for duration_ms, returning the time reached. */
static uint32_t hold(struct tank_level_switch *sw, bool asserted, uint32_t from_ms,
		     uint32_t duration_ms)
{
	const uint32_t interval = sw->config.scan_interval_ms;
	const bool raw = raw_input_for(&sw->config, asserted);
	uint32_t now = from_ms;

	for (uint32_t waited = 0; waited <= duration_ms; waited += interval) {
		now = from_ms + waited;
		zassert_equal(tank_level_switch_sample(sw, raw, now), 0, "sampling failed");
	}

	return now;
}

static struct tank_level_switch_status status_at(const struct tank_level_switch *sw,
						 uint32_t now_ms)
{
	struct tank_level_switch_status status = {0};

	zassert_equal(tank_level_switch_status(sw, now_ms, &status), 0, "status failed");
	return status;
}

/* An initialised reader for the index-th switch in the contract table. */
static struct tank_level_switch reader_for(size_t index)
{
	const struct tank_level_switch_config *config = tank_level_switch_config_at(index);
	struct tank_level_switch sw = {0};

	zassert_not_null(config, "switch %zu is missing from the contract table", index);
	zassert_equal(tank_level_switch_init(&sw, config), 0, "init failed");
	return sw;
}

/* Long enough for a confirmed state to stop being live. */
static uint32_t stale_after(const struct tank_level_switch *sw)
{
	return tank_level_switch_live_window_ms(&sw->config) + 1U;
}

ZTEST_SUITE(safety_level_switch, NULL, NULL, NULL, NULL, NULL);

ZTEST(safety_level_switch, test_contract_comes_from_the_signal_list)
{
	const size_t count = tank_level_switch_config_count();

	zassert_true(count >= 2, "the signal list gives P1-05 two switches, found %zu", count);

	for (size_t i = 0; i < count; i++) {
		const struct tank_level_switch_config *config = tank_level_switch_config_at(i);

		zassert_not_null(config, "switch %zu is missing", i);
		zassert_equal(config->sense, TANK_CONTACT_NORMALLY_CLOSED,
			      "signal %u must be normally closed so a broken wire reads as alarm",
			      config->signal_id);
		zassert_not_equal(config->channel, 0, "signal %u has no channel",
				  config->signal_id);
		zassert_true(config->debounce_ms > 0, "signal %u has no debounce",
			     config->signal_id);
		zassert_true(config->scan_interval_ms > 0, "signal %u has no scan interval",
			     config->signal_id);
		zassert_equal(tank_level_switch_config_by_id(config->signal_id), config,
			      "signal %u does not look up by its own id", config->signal_id);
	}
}

ZTEST(safety_level_switch, test_unknown_signals_and_out_of_range_lookups_are_refused)
{
	zassert_is_null(tank_level_switch_config_by_id(ID_THAT_CANNOT_EXIST));
	zassert_is_null(tank_level_switch_config_at(tank_level_switch_config_count()));
	zassert_equal(tank_level_switch_live_window_ms(NULL), 0);
}

ZTEST(safety_level_switch, test_the_contact_sense_decides_what_an_energised_input_means)
{
	const struct tank_level_switch_config *closed = tank_level_switch_config_at(0);
	struct tank_level_switch_config open_contact = *closed;
	struct tank_level_switch sw = {0};

	open_contact.sense = TANK_CONTACT_NORMALLY_OPEN;
	zassert_equal(tank_level_switch_init(&sw, &open_contact), 0, "init failed");

	/* On a normally open contact an energised input is the assertion itself. */
	const uint32_t now = hold(&sw, true, 0U, open_contact.debounce_ms);

	zassert_equal(status_at(&sw, now).state, TANK_SWITCH_ASSERTED,
		      "a normally open contact asserts when energised");
}

ZTEST(safety_level_switch, test_a_cleared_switch_reads_clear)
{
	for (size_t i = 0; i < tank_level_switch_config_count(); i++) {
		struct tank_level_switch sw = reader_for(i);
		const uint32_t now = hold(&sw, false, 0U, sw.config.debounce_ms * SCANS_PER_HOLD);
		const struct tank_level_switch_status status = status_at(&sw, now);

		zassert_equal(status.state, TANK_SWITCH_CLEAR, "signal %u should read clear",
			      status.signal_id);
		zassert_true(status.live, "a freshly sampled state is live");
	}
}

ZTEST(safety_level_switch, test_an_asserted_switch_reads_asserted)
{
	for (size_t i = 0; i < tank_level_switch_config_count(); i++) {
		struct tank_level_switch sw = reader_for(i);
		const uint32_t now = hold(&sw, true, 0U, sw.config.debounce_ms * SCANS_PER_HOLD);
		const struct tank_level_switch_status status = status_at(&sw, now);

		zassert_equal(status.state, TANK_SWITCH_ASSERTED,
			      "signal %u held asserted, including a broken wire, must read "
			      "asserted and never be smoothed away",
			      status.signal_id);
		zassert_true(status.live, "a freshly sampled state is live");
	}
}

ZTEST(safety_level_switch, test_no_state_is_reported_before_the_debounce_window_passes)
{
	for (size_t i = 0; i < tank_level_switch_config_count(); i++) {
		struct tank_level_switch sw = reader_for(i);
		const struct tank_level_switch_config *config = &sw.config;

		zassert_equal(tank_level_switch_sample(&sw, raw_input_for(config, false), 0U), 0);

		const struct tank_level_switch_status status = status_at(&sw, 0U);

		zassert_equal(status.state, TANK_SWITCH_UNKNOWN,
			      "signal %u must not report a state it has not confirmed",
			      status.signal_id);
		zassert_false(status.live, "an unconfirmed state is not live");
	}
}

ZTEST(safety_level_switch, test_a_transition_is_confirmed_only_after_the_debounce_window)
{
	for (size_t i = 0; i < tank_level_switch_config_count(); i++) {
		struct tank_level_switch sw = reader_for(i);
		const uint32_t debounce = sw.config.debounce_ms;
		uint32_t now = hold(&sw, false, 0U, debounce);

		/* The input asserts, but not for long enough yet. */
		now = hold(&sw, true, now + sw.config.scan_interval_ms,
			   debounce - sw.config.scan_interval_ms * 2U);
		zassert_equal(status_at(&sw, now).state, TANK_SWITCH_CLEAR,
			      "signal %u changed state inside its debounce window",
			      sw.config.signal_id);

		now = hold(&sw, true, now + sw.config.scan_interval_ms, debounce);
		zassert_equal(status_at(&sw, now).state, TANK_SWITCH_ASSERTED,
			      "signal %u did not confirm the transition", sw.config.signal_id);
	}
}

/* A chattering input that never holds a state long enough to be confirmed. */
static uint32_t chatter(struct tank_level_switch *sw, uint32_t from_ms, uint32_t scans)
{
	uint32_t now = from_ms;

	for (uint32_t scan = 0; scan < scans; scan++) {
		now = from_ms + scan * sw->config.scan_interval_ms;
		zassert_equal(tank_level_switch_sample(sw, (scan % 2U) == 0U, now), 0);
	}

	return now;
}

ZTEST(safety_level_switch, test_an_input_that_never_settles_confirms_nothing)
{
	for (size_t i = 0; i < tank_level_switch_config_count(); i++) {
		struct tank_level_switch sw = reader_for(i);
		const uint32_t now = chatter(&sw, 0U, SCANS_PER_HOLD);
		const struct tank_level_switch_status status = status_at(&sw, now);

		zassert_equal(status.state, TANK_SWITCH_UNKNOWN,
			      "signal %u confirmed a state from a chattering input",
			      status.signal_id);
		zassert_false(status.live, "a chattering channel has no live state");
	}
}

ZTEST(safety_level_switch, test_a_confirmed_state_stops_being_live_when_it_stops_being_confirmed)
{
	for (size_t i = 0; i < tank_level_switch_config_count(); i++) {
		struct tank_level_switch sw = reader_for(i);
		const uint32_t confirmed_at = hold(&sw, true, 0U, sw.config.debounce_ms);

		/* Chatter after a confirmed state: the state is kept, not re-confirmed. */
		const uint32_t chattered =
		    chatter(&sw, confirmed_at + sw.config.scan_interval_ms, SCANS_PER_HOLD);
		const uint32_t later = chattered + stale_after(&sw);
		struct tank_level_switch_status status = status_at(&sw, chattered);

		zassert_equal(status.state, TANK_SWITCH_ASSERTED,
			      "signal %u lost its last confirmed state", status.signal_id);

		/* Sampling stops altogether: the same rule covers a dead scan loop. */
		status = status_at(&sw, later);
		zassert_equal(status.state, TANK_SWITCH_ASSERTED, "the last state is still known");
		zassert_false(status.live, "signal %u showed a stale state as live",
			      status.signal_id);
	}
}

ZTEST(safety_level_switch, test_the_millisecond_counter_may_wrap)
{
	for (size_t i = 0; i < tank_level_switch_config_count(); i++) {
		struct tank_level_switch sw = reader_for(i);
		const uint32_t before_wrap = UINT32_MAX - sw.config.debounce_ms;
		const uint32_t now = hold(&sw, true, before_wrap, sw.config.debounce_ms * 2U);
		const struct tank_level_switch_status status = status_at(&sw, now);

		zassert_equal(status.state, TANK_SWITCH_ASSERTED,
			      "signal %u failed to confirm across a counter wrap",
			      status.signal_id);
		zassert_true(status.live, "a state confirmed across a wrap is live");
	}
}

ZTEST(safety_level_switch, test_invalid_arguments_are_refused)
{
	const struct tank_level_switch_config *config = tank_level_switch_config_at(0);
	struct tank_level_switch_config broken = *config;
	struct tank_level_switch sw = {0};
	struct tank_level_switch_status status = {0};

	zassert_equal(tank_level_switch_init(NULL, config), -EINVAL);
	zassert_equal(tank_level_switch_init(&sw, NULL), -EINVAL);

	broken.scan_interval_ms = 0U;
	zassert_equal(tank_level_switch_init(&sw, &broken), -EINVAL,
		      "a channel with no scan interval cannot be debounced");

	broken = *config;
	broken.sense = (enum tank_contact_sense)(TANK_CONTACT_NORMALLY_CLOSED + 1);
	zassert_equal(tank_level_switch_init(&sw, &broken), -EINVAL,
		      "an unknown contact sense must not be guessed at");

	/* An uninitialised reader must not quietly accept samples. */
	struct tank_level_switch uninitialised = {0};

	zassert_equal(tank_level_switch_sample(&uninitialised, true, 0U), -EINVAL);
	zassert_equal(tank_level_switch_sample(NULL, true, 0U), -EINVAL);
	zassert_equal(tank_level_switch_status(NULL, 0U, &status), -EINVAL);
	zassert_equal(tank_level_switch_status(&uninitialised, 0U, NULL), -EINVAL);
}
