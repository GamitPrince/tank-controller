/*
 * ztest suite for the six product temperature reads (S-032, P1-06).
 *
 * The spec's test plan (nominal, open circuit, short, out-of-range, fault
 * register set, one of six failed while five are healthy, wrong chip-select
 * addressing) is driven from the generated contract table, so the ids, chip
 * selects and valid ranges come from interfaces/signals-v1.yaml and are never
 * written into this file.
 *
 * Readings are built directly as decoded struct tank_max31865_reading values
 * rather than through tank_max31865_decode(): that function's own register
 * decode is covered by firmware/tests/hardware_max31865, and this layer takes
 * a decoded reading as its input, so the fixture matches the real interface.
 * A reference resistor of 400 ohms is assumed only to pick realistic raw ADC
 * codes for the open/short checks; the firmware itself does not hardcode it.
 */

#include <zephyr/ztest.h>

#include <errno.h>

#include "product_temperature.h"

#define RREF_OHMS 400.0f
#define TOLERANCE_DEGC 0.01f

/* A healthy decoded reading for the given RTD resistance. */
static struct tank_max31865_reading reading_for(float resistance_ohms)
{
	struct tank_max31865_reading reading = {0};

	reading.resistance_ohms = resistance_ohms;
	reading.raw_code15 = (uint16_t)((resistance_ohms / RREF_OHMS) * 32768.0f);
	reading.fault_bit = false;
	reading.fault_flags = 0U;

	return reading;
}

static struct tank_product_temperature reader_for(size_t index)
{
	const struct tank_product_temperature_config *config =
	    tank_product_temperature_config_at(index);
	struct tank_product_temperature sensor = {0};

	zassert_not_null(config, "sensor %zu is missing from the contract table", index);
	zassert_equal(tank_product_temperature_init(&sensor, config), 0, "init failed");
	return sensor;
}

static struct tank_product_temperature_status
status_at(const struct tank_product_temperature *sensor, uint32_t now_ms)
{
	struct tank_product_temperature_status status = {0};

	zassert_equal(tank_product_temperature_status(sensor, now_ms, &status), 0, "status failed");
	return status;
}

ZTEST_SUITE(product_temperature, NULL, NULL, NULL, NULL, NULL);

ZTEST(product_temperature, test_the_signal_list_gives_six_sensors_with_distinct_chip_selects)
{
	const size_t count = tank_product_temperature_config_count();

	zassert_equal(count, 6, "P1-06 reads six PT100s, found %zu", count);

	int seen_chip_select[7] = {0}; /* index 1..6 used, 0 unused */
	int upper = 0, middle = 0, bottom = 0;

	for (size_t i = 0; i < count; i++) {
		const struct tank_product_temperature_config *config =
		    tank_product_temperature_config_at(i);

		zassert_not_null(config, "sensor %zu is missing", i);
		zassert_true(config->chip_select >= 1 && config->chip_select <= 6,
			     "signal %u has chip select %u outside 1..6", config->signal_id,
			     config->chip_select);
		zassert_equal(seen_chip_select[config->chip_select], 0,
			      "chip select %u is used by more than one sensor",
			      config->chip_select);
		seen_chip_select[config->chip_select] = 1;

		zassert_equal(tank_product_temperature_config_by_id(config->signal_id), config,
			      "signal %u does not look up by its own id", config->signal_id);
		zassert_equal(tank_product_temperature_config_by_chip_select(config->chip_select),
			      config, "chip select %u does not look up to its own sensor",
			      config->chip_select);

		switch (config->level) {
		case TANK_PRODUCT_LEVEL_UPPER:
			upper++;
			break;
		case TANK_PRODUCT_LEVEL_MIDDLE:
			middle++;
			break;
		case TANK_PRODUCT_LEVEL_BOTTOM:
			bottom++;
			break;
		}
	}

	zassert_equal(upper, 2, "two sensors should be mounted at the upper level");
	zassert_equal(middle, 2, "two sensors should be mounted at the middle level");
	zassert_equal(bottom, 2, "two sensors should be mounted at the bottom level");
}

ZTEST(product_temperature, test_before_any_reading_a_sensor_is_unconfigured_and_not_live)
{
	for (size_t i = 0; i < tank_product_temperature_config_count(); i++) {
		struct tank_product_temperature sensor = reader_for(i);
		const struct tank_product_temperature_status status = status_at(&sensor, 0U);

		zassert_equal(status.quality, TANK_QUALITY_UNCONFIGURED,
			      "signal %u should be unconfigured before its first reading",
			      status.signal_id);
		zassert_false(status.live);
	}
}

ZTEST(product_temperature, test_a_nominal_reading_is_good_and_live)
{
	for (size_t i = 0; i < tank_product_temperature_config_count(); i++) {
		struct tank_product_temperature sensor = reader_for(i);
		const struct tank_max31865_reading reading = reading_for(138.5055f); /* 100 degC */

		zassert_equal(tank_product_temperature_update(&sensor, &reading, 0U), 0);

		const struct tank_product_temperature_status status = status_at(&sensor, 0U);

		zassert_equal(status.quality, TANK_QUALITY_GOOD, "signal %u should read good",
			      status.signal_id);
		zassert_true(status.live, "signal %u should be live", status.signal_id);
		zassert_within(status.temperature_degc, 100.0f, TOLERANCE_DEGC);
	}
}

ZTEST(product_temperature, test_an_open_circuit_is_flagged_as_fault_and_excluded)
{
	struct tank_product_temperature sensor = reader_for(0);
	struct tank_max31865_reading reading = reading_for(100.0f);

	reading.fault_bit = true;
	reading.raw_code15 = 32100U; /* saturated near full scale */

	zassert_equal(tank_product_temperature_update(&sensor, &reading, 0U), 0);

	const struct tank_product_temperature_status status = status_at(&sensor, 0U);

	zassert_equal(status.quality, TANK_QUALITY_FAULT,
		      "an open RTD must be flagged as a fault, never silently replaced");
	zassert_false(status.live);
}

ZTEST(product_temperature, test_a_short_is_flagged_as_fault_and_excluded)
{
	struct tank_product_temperature sensor = reader_for(0);
	struct tank_max31865_reading reading = reading_for(1.0f);

	reading.raw_code15 = 5U; /* pinned near zero */

	zassert_equal(tank_product_temperature_update(&sensor, &reading, 0U), 0);

	const struct tank_product_temperature_status status = status_at(&sensor, 0U);

	zassert_equal(status.quality, TANK_QUALITY_FAULT,
		      "a shorted RTD must be flagged as a fault");
	zassert_false(status.live);
}

ZTEST(product_temperature, test_a_fault_register_flag_alone_is_a_fault_even_without_the_fault_bit)
{
	struct tank_product_temperature sensor = reader_for(0);
	struct tank_max31865_reading reading = reading_for(138.5055f); /* otherwise nominal */

	reading.fault_flags = TANK_MAX31865_FAULT_OVER_UNDER_VOLTAGE;

	zassert_equal(tank_product_temperature_update(&sensor, &reading, 0U), 0);

	zassert_equal(status_at(&sensor, 0U).quality, TANK_QUALITY_FAULT,
		      "a fault register flag must withhold the value even if the "
		      "register's own fault bit is clear");
}

ZTEST(product_temperature, test_an_out_of_range_reading_is_reported_but_not_live)
{
	struct tank_product_temperature sensor = reader_for(0); /* valid range 0..200 degC */
	const struct tank_max31865_reading reading = reading_for(183.1875f); /* 220 degC */

	zassert_equal(tank_product_temperature_update(&sensor, &reading, 0U), 0);

	const struct tank_product_temperature_status status = status_at(&sensor, 0U);

	zassert_equal(status.quality, TANK_QUALITY_OUT_OF_RANGE,
		      "a reading outside the valid range must be flagged out of range");
	zassert_false(status.live, "an out-of-range reading must not be shown as live");
	zassert_within(status.temperature_degc, 220.0f, 0.5f,
		       "the value is still reported, not clamped, so a consumer can see how "
		       "far out of range it sits");
}

ZTEST(product_temperature, test_one_of_six_sensors_failed_while_the_other_five_are_healthy)
{
	const size_t count = tank_product_temperature_config_count();
	const size_t failed_index = 2;

	for (size_t i = 0; i < count; i++) {
		struct tank_product_temperature sensor = reader_for(i);
		struct tank_max31865_reading reading = reading_for(138.5055f);

		if (i == failed_index) {
			reading.fault_bit = true;
			reading.raw_code15 = 32100U;
		}

		zassert_equal(tank_product_temperature_update(&sensor, &reading, 0U), 0);

		const struct tank_product_temperature_status status = status_at(&sensor, 0U);

		if (i == failed_index) {
			zassert_equal(status.quality, TANK_QUALITY_FAULT,
				      "sensor %zu should have failed", i);
		} else {
			zassert_equal(status.quality, TANK_QUALITY_GOOD,
				      "sensor %zu should stay healthy while another one fails", i);
			zassert_true(status.live, "sensor %zu should still be live", i);
		}
	}
}

ZTEST(product_temperature, test_chip_select_addressing_keeps_each_sensors_reading_separate)
{
	/* Six distinct resistances, one per sensor; wiring one sensor's reading
	 * to another's chip select, or indexing the contract table out of
	 * order, would show up as a mismatched temperature here.
	 */
	static const float resistance_ohms[6] = {
	    103.90252685546875f, /* 10 degC */
	    115.54080200195312f, /* 40 degC */
	    127.07512664794922f, /* 70 degC */
	    138.50550842285156f, /* 100 degC */
	    149.83192443847656f, /* 130 degC */
	    161.0543975830078f,	 /* 160 degC */
	};
	static const float expected_degc[6] = {10.0f, 40.0f, 70.0f, 100.0f, 130.0f, 160.0f};

	const size_t count = tank_product_temperature_config_count();

	zassert_equal(count, 6);

	for (size_t i = 0; i < count; i++) {
		struct tank_product_temperature sensor = reader_for(i);
		const struct tank_max31865_reading reading = reading_for(resistance_ohms[i]);

		zassert_equal(tank_product_temperature_update(&sensor, &reading, 0U), 0);

		const struct tank_product_temperature_status status = status_at(&sensor, 0U);

		zassert_within(status.temperature_degc, expected_degc[i], 0.1f,
			       "sensor %zu reported another channel's temperature", i);
	}
}

ZTEST(product_temperature, test_a_reading_that_stops_being_refreshed_goes_stale)
{
	for (size_t i = 0; i < tank_product_temperature_config_count(); i++) {
		struct tank_product_temperature sensor = reader_for(i);
		const struct tank_max31865_reading reading = reading_for(138.5055f);

		zassert_equal(tank_product_temperature_update(&sensor, &reading, 0U), 0);

		const uint32_t stale_at =
		    tank_product_temperature_live_window_ms(&sensor.config) + 1U;
		const struct tank_product_temperature_status status = status_at(&sensor, stale_at);

		zassert_equal(status.quality, TANK_QUALITY_STALE,
			      "signal %u should go stale once it stops being refreshed",
			      status.signal_id);
		zassert_false(status.live, "a stale reading must never be shown as live");
	}
}

ZTEST(product_temperature, test_the_fault_deadline_is_within_the_sixty_second_requirement)
{
	for (size_t i = 0; i < tank_product_temperature_config_count(); i++) {
		const struct tank_product_temperature_config *config =
		    tank_product_temperature_config_at(i);
		const uint32_t deadline_ms = tank_product_temperature_fault_deadline_ms(config);

		zassert_true(deadline_ms > 0, "signal %u has no fault deadline", config->signal_id);
		zassert_true(deadline_ms <= TANK_PRODUCT_TEMPERATURE_FAULT_DEADLINE_MS,
			     "signal %u's fault deadline of %u ms exceeds the 60 s acceptance "
			     "criterion",
			     config->signal_id, deadline_ms);
	}
}

ZTEST(product_temperature, test_invalid_arguments_are_refused)
{
	const struct tank_product_temperature_config *config =
	    tank_product_temperature_config_at(0);
	struct tank_product_temperature_config broken = *config;
	struct tank_product_temperature sensor = {0};
	const struct tank_max31865_reading reading = reading_for(138.5055f);
	struct tank_product_temperature_status status = {0};

	zassert_equal(tank_product_temperature_init(NULL, config), -EINVAL);
	zassert_equal(tank_product_temperature_init(&sensor, NULL), -EINVAL);

	broken.chip_select = 0;
	zassert_equal(tank_product_temperature_init(&sensor, &broken), -EINVAL,
		      "chip select 0 is outside the MAX31865's 1..6");

	broken = *config;
	broken.chip_select = 7;
	zassert_equal(tank_product_temperature_init(&sensor, &broken), -EINVAL,
		      "chip select 7 is outside the MAX31865's 1..6");

	broken = *config;
	broken.update_rate_ms = 0U;
	zassert_equal(tank_product_temperature_init(&sensor, &broken), -EINVAL,
		      "a channel with no update rate cannot report staleness");

	broken = *config;
	broken.valid_low_degc = broken.valid_high_degc;
	zassert_equal(tank_product_temperature_init(&sensor, &broken), -EINVAL,
		      "an empty valid range must be rejected");

	broken = *config;
	broken.level = (enum tank_product_level)99;
	zassert_equal(tank_product_temperature_init(&sensor, &broken), -EINVAL,
		      "an unknown mounting level must not be guessed at");

	struct tank_product_temperature uninitialised = {0};

	zassert_equal(tank_product_temperature_update(&uninitialised, &reading, 0U), -EINVAL);
	zassert_equal(tank_product_temperature_update(NULL, &reading, 0U), -EINVAL);
	zassert_equal(tank_product_temperature_update(&uninitialised, NULL, 0U), -EINVAL);
	zassert_equal(tank_product_temperature_status(NULL, 0U, &status), -EINVAL);
	zassert_equal(tank_product_temperature_status(&uninitialised, 0U, NULL), -EINVAL);

	zassert_is_null(tank_product_temperature_config_by_id(0U));
	zassert_is_null(tank_product_temperature_config_by_chip_select(0U));
	zassert_is_null(
	    tank_product_temperature_config_at(tank_product_temperature_config_count()));
	zassert_equal(tank_product_temperature_live_window_ms(NULL), 0);
	zassert_equal(tank_product_temperature_fault_deadline_ms(NULL), 0);
}
