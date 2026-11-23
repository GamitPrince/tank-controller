/*
 * ztest suite for the status-only alarm and trip contact reads (S-031, P1-09).
 *
 * The spec's test plan asks for each alarm asserted and cleared, several at
 * once, an open circuit (must read as alarm), chatter shorter than the
 * debounce, and chatter longer than it, on native_sim with simulated
 * optocoupler inputs. Every case below is driven from the generated contract
 * table, so the ids, channel numbers, contact senses and debounce figures
 * come from interfaces/signals-v1.yaml and are never written into this file.
 *
 * The debounce/liveness state machine under test is tank_level_switch from
 * story P1-05 (level_switch.h): this story reuses it rather than
 * reimplementing it, so these tests exercise that engine against the P1-09
 * contract table (alarm_input.h), not a second copy of its logic.
 */

#include <zephyr/ztest.h>

#include <errno.h>

#include "alarm_input.h"

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

/* An initialised reader for the index-th alarm contact in the contract table. */
static struct tank_level_switch reader_for(size_t index)
{
	const struct tank_level_switch_config *config = tank_alarm_input_config_at(index);
	struct tank_level_switch sw = {0};

	zassert_not_null(config, "alarm contact %zu is missing from the contract table", index);
	zassert_equal(tank_level_switch_init(&sw, config), 0, "init failed");
	return sw;
}

ZTEST_SUITE(safety_alarm_input, NULL, NULL, NULL, NULL, NULL);

ZTEST(safety_alarm_input, test_contract_comes_from_the_signal_list)
{
	const size_t count = tank_alarm_input_config_count();

	zassert_true(count >= 6, "the signal list gives P1-09 six alarm contacts, found %zu",
		     count);

	for (size_t i = 0; i < count; i++) {
		const struct tank_level_switch_config *config = tank_alarm_input_config_at(i);

		zassert_not_null(config, "alarm contact %zu is missing", i);
		zassert_equal(config->sense, TANK_CONTACT_NORMALLY_CLOSED,
			      "signal %u must be normally closed so a broken wire reads as alarm",
			      config->signal_id);
		zassert_not_equal(config->channel, 0, "signal %u has no channel",
				  config->signal_id);
		zassert_equal(config->debounce_ms, 200U,
			      "signal %u does not use the 200 ms "
			      "debounce decided for the alarm channels",
			      config->signal_id);
		zassert_true(config->scan_interval_ms > 0, "signal %u has no scan interval",
			     config->signal_id);
		zassert_equal(tank_alarm_input_config_by_id(config->signal_id), config,
			      "signal %u does not look up by its own id", config->signal_id);
	}
}

ZTEST(safety_alarm_input, test_unknown_signals_and_out_of_range_lookups_are_refused)
{
	zassert_is_null(tank_alarm_input_config_by_id(ID_THAT_CANNOT_EXIST));
	zassert_is_null(tank_alarm_input_config_at(tank_alarm_input_config_count()));
}

ZTEST(safety_alarm_input, test_each_alarm_reads_clear_when_healthy)
{
	for (size_t i = 0; i < tank_alarm_input_config_count(); i++) {
		struct tank_level_switch sw = reader_for(i);
		const uint32_t now = hold(&sw, false, 0U, sw.config.debounce_ms * SCANS_PER_HOLD);
		const struct tank_level_switch_status status = status_at(&sw, now);

		zassert_equal(status.state, TANK_SWITCH_CLEAR, "signal %u should read clear",
			      status.signal_id);
		zassert_true(status.live, "a freshly sampled state is live");
	}
}

ZTEST(safety_alarm_input, test_each_alarm_reads_asserted_including_an_open_circuit)
{
	for (size_t i = 0; i < tank_alarm_input_config_count(); i++) {
		struct tank_level_switch sw = reader_for(i);

		/* A normally closed contact de-energised is exactly what a broken wire
		 * looks like: there is only one raw state here, and it must read
		 * asserted either way.
		 */
		const uint32_t now = hold(&sw, true, 0U, sw.config.debounce_ms * SCANS_PER_HOLD);
		const struct tank_level_switch_status status = status_at(&sw, now);

		zassert_equal(status.state, TANK_SWITCH_ASSERTED,
			      "signal %u must read asserted when de-energised or open-circuit",
			      status.signal_id);
		zassert_true(status.live, "a freshly sampled state is live");
	}
}

/* The optocoupler block has 16 channels; the contract table is never larger. */
#define MAX_ALARM_INPUTS 16U

ZTEST(safety_alarm_input, test_several_alarms_asserted_at_once_stay_independent)
{
	const size_t count = tank_alarm_input_config_count();
	struct tank_level_switch readers[MAX_ALARM_INPUTS];
	uint32_t confirmed_at[MAX_ALARM_INPUTS];

	zassert_true(count <= MAX_ALARM_INPUTS, "more alarm contacts than optocoupler channels");

	for (size_t i = 0; i < count; i++) {
		readers[i] = reader_for(i);
	}

	/* Assert every odd-indexed contact, leave the even-indexed ones clear. */
	for (size_t i = 0; i < count; i++) {
		const bool asserted = (i % 2U) == 1U;

		confirmed_at[i] = hold(&readers[i], asserted, 0U, readers[i].config.debounce_ms);
	}

	for (size_t i = 0; i < count; i++) {
		const bool expect_asserted = (i % 2U) == 1U;
		const struct tank_level_switch_status status =
		    status_at(&readers[i], confirmed_at[i]);

		zassert_equal(
		    status.state, expect_asserted ? TANK_SWITCH_ASSERTED : TANK_SWITCH_CLEAR,
		    "signal %u was affected by another channel's state", status.signal_id);
	}
}

ZTEST(safety_alarm_input, test_a_transition_is_confirmed_only_after_the_debounce_window)
{
	for (size_t i = 0; i < tank_alarm_input_config_count(); i++) {
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

ZTEST(safety_alarm_input, test_chatter_shorter_than_the_debounce_window_confirms_nothing)
{
	for (size_t i = 0; i < tank_alarm_input_config_count(); i++) {
		struct tank_level_switch sw = reader_for(i);
		const uint32_t scans_inside_one_debounce_window =
		    sw.config.debounce_ms / sw.config.scan_interval_ms;
		const uint32_t now = chatter(&sw, 0U, scans_inside_one_debounce_window);
		const struct tank_level_switch_status status = status_at(&sw, now);

		zassert_equal(status.state, TANK_SWITCH_UNKNOWN,
			      "signal %u confirmed a state from brief chatter", status.signal_id);
		zassert_false(status.live, "a chattering channel has no live state");
	}
}

ZTEST(safety_alarm_input, test_chatter_longer_than_the_debounce_window_still_confirms_nothing)
{
	for (size_t i = 0; i < tank_alarm_input_config_count(); i++) {
		struct tank_level_switch sw = reader_for(i);
		const uint32_t now = chatter(&sw, 0U, SCANS_PER_HOLD);
		const struct tank_level_switch_status status = status_at(&sw, now);

		zassert_equal(status.state, TANK_SWITCH_UNKNOWN,
			      "signal %u confirmed a state from sustained chatter",
			      status.signal_id);
		zassert_false(status.live, "a chattering channel has no live state");
	}
}

ZTEST(safety_alarm_input, test_a_stuck_alarm_stays_asserted_and_then_goes_stale)
{
	for (size_t i = 0; i < tank_alarm_input_config_count(); i++) {
		struct tank_level_switch sw = reader_for(i);
		const uint32_t confirmed_at = hold(&sw, true, 0U, sw.config.debounce_ms);
		const uint32_t stale_at =
		    confirmed_at + tank_level_switch_live_window_ms(&sw.config) + 1U;

		/* Sampling stops: a stuck input must not be smoothed into "healthy". */
		struct tank_level_switch_status status = status_at(&sw, confirmed_at);

		zassert_equal(status.state, TANK_SWITCH_ASSERTED, "signal %u lost its stuck state",
			      status.signal_id);
		zassert_true(status.live, "a freshly confirmed state is live");

		status = status_at(&sw, stale_at);
		zassert_equal(status.state, TANK_SWITCH_ASSERTED,
			      "signal %u's last known state must still be asserted, never "
			      "silently replaced",
			      status.signal_id);
		zassert_false(status.live, "a stale state must never be shown as live");
	}
}
