/*
 * ztest suite for the equipment status reads (S-033, P1-27).
 *
 * The spec's test plan asks, on native_sim with simulated optocoupler inputs,
 * for each channel on and off, all seven at once, chatter shorter than the
 * debounce (suppressed), chatter longer than it (reported) and a channel that
 * never settles. Every case is driven from the generated contract table, so
 * the ids, channels, contact senses and debounce figures come from
 * interfaces/signals-v1.yaml and are never written into this file.
 *
 * These contacts are normally open, so an energised input means the equipment
 * is running: TANK_SWITCH_ASSERTED is "running" and TANK_SWITCH_CLEAR is "not
 * running". The state machine is the generic one from safety/level_switch.h;
 * only the contract table and the placement are this story's.
 */

#include <zephyr/ztest.h>

#include <errno.h>

#include "equipment_status.h"

/* The EE's figure, decided 20 Nov 2026; the list is the source, this pins it. */
#define EXPECTED_DEBOUNCE_MS 5000U

/* An id below the signal list's 1000-block floor cannot name a real signal. */
#define ID_THAT_CANNOT_EXIST 0U

/* Enough scans to prove a state keeps being reported, without being slow. */
#define SCANS_PER_HOLD 20U

#define MAX_CHANNELS 16U

/* Sample one steady input for duration_ms, returning the time reached. */
static uint32_t hold(struct tank_level_switch *sw, bool running, uint32_t from_ms,
		     uint32_t duration_ms)
{
	const uint32_t interval = sw->config.scan_interval_ms;
	uint32_t now = from_ms;

	/* Normally open: a closed, energised contact is the equipment running. */
	for (uint32_t waited = 0; waited <= duration_ms; waited += interval) {
		now = from_ms + waited;
		zassert_equal(tank_level_switch_sample(sw, running, now), 0, "sampling failed");
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

/* An initialised reader for the index-th contact in the contract table. */
static struct tank_level_switch reader_for(size_t index)
{
	const struct tank_level_switch_config *config = tank_equipment_status_config_at(index);
	struct tank_level_switch sw = {0};

	zassert_not_null(config, "contact %zu is missing from the contract table", index);
	zassert_equal(tank_level_switch_init(&sw, config), 0, "init failed");
	return sw;
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

ZTEST_SUITE(equipment_status, NULL, NULL, NULL, NULL, NULL);

ZTEST(equipment_status, test_contract_comes_from_the_signal_list)
{
	const size_t count = tank_equipment_status_config_count();
	bool channel_used[MAX_CHANNELS + 1U] = {false};

	zassert_equal(count, 7, "the signal list gives P1-27 seven contacts, found %zu", count);

	for (size_t i = 0; i < count; i++) {
		const struct tank_level_switch_config *config = tank_equipment_status_config_at(i);

		zassert_not_null(config, "contact %zu is missing", i);
		zassert_equal(config->sense, TANK_CONTACT_NORMALLY_OPEN,
			      "signal %u must be normally open: open means not running",
			      config->signal_id);
		zassert_equal(config->debounce_ms, EXPECTED_DEBOUNCE_MS,
			      "signal %u has the wrong debounce", config->signal_id);
		zassert_true(config->scan_interval_ms > 0, "signal %u has no scan interval",
			     config->signal_id);
		zassert_true(config->channel >= 3 && config->channel <= 9,
			     "signal %u is on channel %u, outside the equipment channels 3 to 9",
			     config->signal_id, config->channel);
		zassert_false(channel_used[config->channel], "channel %u is used twice",
			      config->channel);
		channel_used[config->channel] = true;
		zassert_equal(tank_equipment_status_config_by_id(config->signal_id), config,
			      "signal %u does not look up by its own id", config->signal_id);
	}
}

ZTEST(equipment_status, test_unknown_signals_and_out_of_range_lookups_are_refused)
{
	zassert_is_null(tank_equipment_status_config_by_id(ID_THAT_CANNOT_EXIST));
	zassert_is_null(tank_equipment_status_config_at(tank_equipment_status_config_count()));
}

ZTEST(equipment_status, test_a_closed_contact_reads_running)
{
	for (size_t i = 0; i < tank_equipment_status_config_count(); i++) {
		struct tank_level_switch sw = reader_for(i);
		const uint32_t now = hold(&sw, true, 0U, sw.config.debounce_ms * 2U);
		const struct tank_level_switch_status status = status_at(&sw, now);

		zassert_equal(status.state, TANK_SWITCH_ASSERTED,
			      "signal %u with a closed contact should read running",
			      status.signal_id);
		zassert_true(status.live, "a freshly sampled state is live");
	}
}

ZTEST(equipment_status, test_an_open_contact_reads_not_running)
{
	for (size_t i = 0; i < tank_equipment_status_config_count(); i++) {
		struct tank_level_switch sw = reader_for(i);
		const uint32_t now = hold(&sw, false, 0U, sw.config.debounce_ms * 2U);
		const struct tank_level_switch_status status = status_at(&sw, now);

		zassert_equal(status.state, TANK_SWITCH_CLEAR,
			      "signal %u with an open contact, a broken wire included, should read "
			      "not running",
			      status.signal_id);
		zassert_true(status.live, "a freshly sampled state is live");
	}
}

ZTEST(equipment_status, test_all_seven_channels_are_read_independently_at_once)
{
	struct tank_level_switch readers[MAX_CHANNELS];
	const size_t count = tank_equipment_status_config_count();

	zassert_true(count <= MAX_CHANNELS);

	for (size_t i = 0; i < count; i++) {
		readers[i] = reader_for(i);
	}

	/* Even-numbered contacts closed, odd-numbered open, all sampled together. */
	uint32_t now = 0U;

	for (uint32_t scan = 0; scan < SCANS_PER_HOLD * 10U; scan++) {
		now = scan * readers[0].config.scan_interval_ms;

		for (size_t i = 0; i < count; i++) {
			zassert_equal(tank_level_switch_sample(&readers[i], (i % 2U) == 0U, now),
				      0);
		}
	}

	for (size_t i = 0; i < count; i++) {
		const struct tank_level_switch_status status = status_at(&readers[i], now);

		zassert_equal(status.state,
			      ((i % 2U) == 0U) ? TANK_SWITCH_ASSERTED : TANK_SWITCH_CLEAR,
			      "signal %u took another channel's state", status.signal_id);
		zassert_true(status.live);
	}
}

ZTEST(equipment_status, test_no_state_is_reported_before_the_debounce_window_passes)
{
	for (size_t i = 0; i < tank_equipment_status_config_count(); i++) {
		struct tank_level_switch sw = reader_for(i);

		zassert_equal(tank_level_switch_sample(&sw, true, 0U), 0);

		const struct tank_level_switch_status status = status_at(&sw, 0U);

		zassert_equal(status.state, TANK_SWITCH_UNKNOWN,
			      "signal %u must not report a state it has not confirmed",
			      status.signal_id);
		zassert_false(status.live, "an unconfirmed state is not live");
	}
}

ZTEST(equipment_status, test_a_pulse_shorter_than_the_debounce_is_suppressed)
{
	for (size_t i = 0; i < tank_equipment_status_config_count(); i++) {
		struct tank_level_switch sw = reader_for(i);
		const uint32_t scan = sw.config.scan_interval_ms;
		uint32_t now = hold(&sw, false, 0U, sw.config.debounce_ms);

		/* A contactor starts and drops again inside the debounce window. */
		now = hold(&sw, true, now + scan, sw.config.debounce_ms - scan * 2U);
		now = hold(&sw, false, now + scan, scan * 2U);

		zassert_equal(status_at(&sw, now).state, TANK_SWITCH_CLEAR,
			      "signal %u reported a pulse shorter than its debounce",
			      sw.config.signal_id);
	}
}

ZTEST(equipment_status, test_a_change_is_reported_once_it_has_held_for_the_debounce_window)
{
	for (size_t i = 0; i < tank_equipment_status_config_count(); i++) {
		struct tank_level_switch sw = reader_for(i);
		uint32_t now = hold(&sw, false, 0U, sw.config.debounce_ms);

		zassert_equal(status_at(&sw, now).state, TANK_SWITCH_CLEAR);

		/* The equipment starts and stays running, longer than the debounce. */
		const uint32_t started = now + sw.config.scan_interval_ms;

		now = hold(&sw, true, started, sw.config.debounce_ms);

		zassert_equal(status_at(&sw, now).state, TANK_SWITCH_ASSERTED,
			      "signal %u did not report a change that held past its debounce",
			      sw.config.signal_id);
		zassert_true(now - started <= sw.config.debounce_ms + sw.config.scan_interval_ms,
			     "signal %u took longer than the scan and debounce window",
			     sw.config.signal_id);
	}
}

ZTEST(equipment_status, test_an_input_that_never_settles_confirms_nothing)
{
	for (size_t i = 0; i < tank_equipment_status_config_count(); i++) {
		struct tank_level_switch sw = reader_for(i);
		const uint32_t now = chatter(&sw, 0U, SCANS_PER_HOLD);
		const struct tank_level_switch_status status = status_at(&sw, now);

		zassert_equal(status.state, TANK_SWITCH_UNKNOWN,
			      "signal %u confirmed a state from a chattering input",
			      status.signal_id);
		zassert_false(status.live, "a chattering channel has no live state");
	}
}

ZTEST(equipment_status, test_a_confirmed_state_stops_being_live_when_sampling_stops)
{
	for (size_t i = 0; i < tank_equipment_status_config_count(); i++) {
		struct tank_level_switch sw = reader_for(i);
		const uint32_t confirmed_at = hold(&sw, true, 0U, sw.config.debounce_ms);
		const uint32_t later =
		    confirmed_at + tank_level_switch_live_window_ms(&sw.config) + 1U;
		const struct tank_level_switch_status status = status_at(&sw, later);

		zassert_equal(status.state, TANK_SWITCH_ASSERTED, "the last state is still known");
		zassert_false(status.live, "signal %u showed a stale state as live",
			      status.signal_id);
	}
}

ZTEST(equipment_status, test_the_debounce_is_configuration_not_a_constant)
{
	const struct tank_level_switch_config *config = tank_equipment_status_config_at(0);
	struct tank_level_switch_config shorter = *config;
	struct tank_level_switch sw = {0};

	shorter.debounce_ms = config->scan_interval_ms * 2U;
	zassert_equal(tank_level_switch_init(&sw, &shorter), 0, "init failed");

	const uint32_t now = hold(&sw, true, 0U, shorter.debounce_ms);

	zassert_equal(status_at(&sw, now).state, TANK_SWITCH_ASSERTED,
		      "a changed debounce must change when a state is confirmed");
}
