/*
 * ztest suite for the 4-20 mA level reads (S-034, P1-04).
 *
 * Ids, channels and valid ranges come from the generated contract table, so
 * they are never written into this file. Readings are built directly as
 * decoded struct tank_ad4111_reading values: the byte-level decode is covered
 * by firmware/tests/hardware_ad4111, and this layer takes a decoded reading.
 */

#include <zephyr/ztest.h>

#include <errno.h>
#include <stddef.h>

#include "loop_level.h"

#define TOLERANCE_MA 0.001f
#define SCAN_MS 1000U

static struct tank_ad4111_reading reading_for(uint8_t channel, float current_ma)
{
	struct tank_ad4111_reading reading = {0};

	reading.channel = channel;
	reading.current_ma = current_ma;
	return reading;
}

static struct tank_loop_level level_for(size_t index)
{
	const struct tank_loop_level_config *config = tank_loop_level_config_at(index);
	struct tank_loop_level level = {0};

	zassert_not_null(config, "channel %zu is missing from the contract table", index);
	zassert_equal(tank_loop_level_init(&level, config), 0, "init failed");
	return level;
}

static struct tank_loop_level_status status_of(const struct tank_loop_level *level, uint32_t now_ms)
{
	struct tank_loop_level_status status = {0};

	zassert_equal(tank_loop_level_status(level, now_ms, &status), 0);
	return status;
}

static void feed(struct tank_loop_level *level, float current_ma, uint32_t now_ms)
{
	const struct tank_ad4111_reading reading = reading_for(level->config.channel, current_ma);

	zassert_equal(tank_loop_level_update(level, &reading, now_ms), 0);
}

ZTEST_SUITE(measurement_loop_level, NULL, NULL, NULL, NULL, NULL);

ZTEST(measurement_loop_level, test_contract_has_radar_on_channel_1_and_pressure_on_channel_2)
{
	zassert_equal(tank_loop_level_config_count(), 2U);
	zassert_equal(tank_loop_level_config_by_id(1001)->channel, 1U);
	zassert_equal(tank_loop_level_config_by_id(1002)->channel, 2U);
	zassert_equal(tank_loop_level_config_by_channel(1)->signal_id, 1001U);
	zassert_equal(tank_loop_level_config_by_channel(2)->signal_id, 1002U);
	zassert_is_null(tank_loop_level_config_by_id(9999));
	zassert_is_null(tank_loop_level_config_by_channel(3));
	zassert_is_null(tank_loop_level_config_at(2));
}

ZTEST(measurement_loop_level, test_nominal_current_is_good_and_live)
{
	for (size_t i = 0; i < tank_loop_level_config_count(); i++) {
		struct tank_loop_level level = level_for(i);

		feed(&level, 12.0f, 5000U);

		const struct tank_loop_level_status s = status_of(&level, 5000U);

		zassert_equal(s.quality, TANK_QUALITY_GOOD);
		zassert_true(s.live);
		zassert_within(s.current_ma, 12.0f, TOLERANCE_MA);
		zassert_equal(s.signal_id, level.config.signal_id);
	}
}

ZTEST(measurement_loop_level, test_the_ends_of_the_valid_range_are_still_good)
{
	struct tank_loop_level level = level_for(0);

	feed(&level, level.config.valid_low_ma, 0U);
	zassert_equal(status_of(&level, 0U).quality, TANK_QUALITY_GOOD);
	feed(&level, level.config.valid_high_ma, 0U);
	zassert_equal(status_of(&level, 0U).quality, TANK_QUALITY_GOOD);
}

ZTEST(measurement_loop_level, test_below_4_ma_is_out_of_range_and_not_clamped)
{
	struct tank_loop_level level = level_for(0);

	feed(&level, 3.8f, 0U);

	const struct tank_loop_level_status s = status_of(&level, 0U);

	zassert_equal(s.quality, TANK_QUALITY_OUT_OF_RANGE);
	zassert_false(s.live);
	zassert_within(s.current_ma, 3.8f, TOLERANCE_MA);
}

ZTEST(measurement_loop_level, test_above_20_ma_is_out_of_range_and_not_clamped)
{
	struct tank_loop_level level = level_for(0);

	feed(&level, 20.5f, 0U);

	const struct tank_loop_level_status s = status_of(&level, 0U);

	zassert_equal(s.quality, TANK_QUALITY_OUT_OF_RANGE);
	zassert_false(s.live);
	zassert_within(s.current_ma, 20.5f, TOLERANCE_MA);
}

ZTEST(measurement_loop_level, test_open_circuit_is_a_fault_with_no_value)
{
	struct tank_loop_level level = level_for(0);

	feed(&level, 12.0f, 0U);
	feed(&level, 0.0f, SCAN_MS);

	const struct tank_loop_level_status s = status_of(&level, SCAN_MS);

	zassert_equal(s.quality, TANK_QUALITY_FAULT);
	zassert_false(s.live);
	zassert_within(s.current_ma, 0.0f, TOLERANCE_MA);
}

ZTEST(measurement_loop_level, test_a_current_far_above_range_is_a_fault)
{
	struct tank_loop_level level = level_for(0);

	feed(&level, 24.0f, 0U);
	zassert_equal(status_of(&level, 0U).quality, TANK_QUALITY_FAULT);
}

ZTEST(measurement_loop_level, test_each_chip_error_flag_is_a_fault_even_with_a_plausible_current)
{
	struct tank_loop_level level = level_for(0);
	struct tank_ad4111_reading reading = reading_for(level.config.channel, 12.0f);

	reading.not_ready = true;
	zassert_equal(tank_loop_level_update(&level, &reading, 0U), 0);
	zassert_equal(status_of(&level, 0U).quality, TANK_QUALITY_FAULT);

	reading.not_ready = false;
	reading.adc_error = true;
	zassert_equal(tank_loop_level_update(&level, &reading, 0U), 0);
	zassert_equal(status_of(&level, 0U).quality, TANK_QUALITY_FAULT);

	reading.adc_error = false;
	reading.crc_error = true;
	zassert_equal(tank_loop_level_update(&level, &reading, 0U), 0);
	zassert_equal(status_of(&level, 0U).quality, TANK_QUALITY_FAULT);

	reading.crc_error = false;
	reading.reg_error = true;
	zassert_equal(tank_loop_level_update(&level, &reading, 0U), 0);
	zassert_equal(status_of(&level, 0U).quality, TANK_QUALITY_FAULT);
}

ZTEST(measurement_loop_level, test_a_fault_never_shows_the_previous_good_value)
{
	struct tank_loop_level level = level_for(0);

	feed(&level, 15.0f, 0U);
	feed(&level, 0.0f, SCAN_MS);

	const struct tank_loop_level_status s = status_of(&level, 2U * SCAN_MS);

	zassert_equal(s.quality, TANK_QUALITY_FAULT);
	zassert_false(s.live);
	zassert_within(s.current_ma, 0.0f, TOLERANCE_MA);
}

ZTEST(measurement_loop_level, test_a_fault_recovers_on_the_next_good_reading)
{
	struct tank_loop_level level = level_for(0);

	feed(&level, 0.0f, 0U);
	feed(&level, 10.0f, SCAN_MS);
	zassert_equal(status_of(&level, SCAN_MS).quality, TANK_QUALITY_GOOD);
}

ZTEST(measurement_loop_level, test_each_channel_is_independent)
{
	struct tank_loop_level radar = level_for(0);
	struct tank_loop_level pressure = level_for(1);

	feed(&radar, 0.0f, 0U);
	feed(&pressure, 12.0f, 0U);

	zassert_equal(status_of(&radar, 0U).quality, TANK_QUALITY_FAULT);
	zassert_equal(status_of(&pressure, 0U).quality, TANK_QUALITY_GOOD);
	zassert_within(status_of(&pressure, 0U).current_ma, 12.0f, TOLERANCE_MA);
}

ZTEST(measurement_loop_level, test_a_conversion_for_another_channel_is_rejected)
{
	struct tank_loop_level radar = level_for(0);
	const uint8_t other = (radar.config.channel == 1U) ? 2U : 1U;
	const struct tank_ad4111_reading reading = reading_for(other, 12.0f);

	zassert_equal(tank_loop_level_update(&radar, &reading, 0U), -EINVAL);
	zassert_equal(status_of(&radar, 0U).quality, TANK_QUALITY_UNCONFIGURED);
}

ZTEST(measurement_loop_level, test_before_the_first_reading_the_channel_is_unconfigured)
{
	struct tank_loop_level level = level_for(0);
	const struct tank_loop_level_status s = status_of(&level, 0U);

	zassert_equal(s.quality, TANK_QUALITY_UNCONFIGURED);
	zassert_false(s.live);
}

ZTEST(measurement_loop_level, test_a_reading_goes_stale_when_no_longer_refreshed)
{
	struct tank_loop_level level = level_for(0);
	const uint32_t window = tank_loop_level_live_window_ms(&level.config);

	feed(&level, 12.0f, 1000U);
	zassert_equal(status_of(&level, 1000U + window).quality, TANK_QUALITY_GOOD);

	const struct tank_loop_level_status s = status_of(&level, 1000U + window + 1U);

	zassert_equal(s.quality, TANK_QUALITY_STALE);
	zassert_false(s.live);
	zassert_equal(s.age_ms, window + 1U);
}

ZTEST(measurement_loop_level, test_a_fault_does_not_turn_stale)
{
	struct tank_loop_level level = level_for(0);

	feed(&level, 0.0f, 0U);
	zassert_equal(status_of(&level, 10U * SCAN_MS).quality, TANK_QUALITY_FAULT);
}

ZTEST(measurement_loop_level, test_staleness_survives_the_millisecond_counter_wrapping)
{
	struct tank_loop_level level = level_for(0);

	feed(&level, 12.0f, UINT32_MAX - 500U);
	zassert_equal(status_of(&level, 500U).quality, TANK_QUALITY_GOOD);
}

ZTEST(measurement_loop_level, test_bad_arguments_are_rejected)
{
	struct tank_loop_level level = level_for(0);
	struct tank_loop_level_config config = level.config;
	struct tank_loop_level fresh = {0};
	struct tank_loop_level_status status = {0};
	const struct tank_ad4111_reading reading = reading_for(level.config.channel, 12.0f);

	zassert_equal(tank_loop_level_init(NULL, &config), -EINVAL);
	zassert_equal(tank_loop_level_init(&fresh, NULL), -EINVAL);

	config.channel = 0U;
	zassert_equal(tank_loop_level_init(&fresh, &config), -EINVAL);
	config = level.config;
	config.channel = 3U;
	zassert_equal(tank_loop_level_init(&fresh, &config), -EINVAL);
	config = level.config;
	config.update_rate_ms = 0U;
	zassert_equal(tank_loop_level_init(&fresh, &config), -EINVAL);
	config = level.config;
	config.valid_low_ma = config.valid_high_ma;
	zassert_equal(tank_loop_level_init(&fresh, &config), -EINVAL);

	zassert_equal(tank_loop_level_update(NULL, &reading, 0U), -EINVAL);
	zassert_equal(tank_loop_level_update(&level, NULL, 0U), -EINVAL);
	zassert_equal(tank_loop_level_update(&fresh, &reading, 0U), -EINVAL);
	zassert_equal(tank_loop_level_status(NULL, 0U, &status), -EINVAL);
	zassert_equal(tank_loop_level_status(&level, 0U, NULL), -EINVAL);
	zassert_equal(tank_loop_level_live_window_ms(NULL), 0U);
}
