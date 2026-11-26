/*
 * ztest suite for the scan builder (S-058, P1-12): every input's status turns
 * into the record's scaled value, quality and age, faults carry no value, an
 * unknown contact is a fault, and the scan it builds encodes.
 */

#include <errno.h>

#include <zephyr/ztest.h>

#include "scan_builder.h"

#define SL 1U
#define SEQ 42U
#define T0 1000U
#define LATER_MS 10000U
#define DEBOUNCE_MS 200U
#define MID_CODE15 10000U
#define R_85_DEGC 132.8034f
#define R_250_DEGC 194.0981f
#define EPOCH_MS 1795000000000ULL

static uint8_t boot_id[TANK_BOOT_ID_LEN];
static const struct tank_boot_time_config bt_cfg = {.agreement_limit_ms = 1000U};
static const struct tank_loop_level_config loop_cfg = {.signal_id = 1001U,
						       .channel = 1U,
						       .update_rate_ms = 1000U,
						       .valid_low_ma = 4.0f,
						       .valid_high_ma = 20.0f};
static const struct tank_product_temperature_config temp_cfg = {.signal_id = 2001U,
								.chip_select = 1U,
								.level = TANK_PRODUCT_LEVEL_UPPER,
								.orientation_deg = 0U,
								.update_rate_ms = 1000U,
								.valid_low_degc = 0.0f,
								.valid_high_degc = 200.0f};
static const struct tank_level_switch_config contact_cfg = {.signal_id = 3001U,
							    .channel = 1U,
							    .sense = TANK_CONTACT_NORMALLY_CLOSED,
							    .debounce_ms = DEBOUNCE_MS,
							    .scan_interval_ms = 50U};

static struct tank_boot_time bt;
static struct tank_loop_level levels[2];
static struct tank_product_temperature temps[2];
static struct tank_level_switch contacts[TANK_SCAN_MAX_READINGS + 1U];
static struct tank_scan scan;

static void feed_loop(struct tank_loop_level *l, float ma, bool adc_error, uint32_t now_ms)
{
	struct tank_ad4111_reading r = {.current_ma = ma, .channel = 1U, .adc_error = adc_error};

	zassert_ok(tank_loop_level_update(l, &r, now_ms));
}

static void feed_temp(struct tank_product_temperature *t, float ohms, bool fault, uint32_t now_ms)
{
	struct tank_max31865_reading r = {
	    .resistance_ohms = ohms, .raw_code15 = MID_CODE15, .fault_bit = fault};

	zassert_ok(tank_product_temperature_update(t, &r, now_ms));
}

/* Hold a normally closed contact at one level until it survives the debounce. */
static void confirm_contact(struct tank_level_switch *sw, bool energised, uint32_t now_ms)
{
	zassert_ok(tank_level_switch_sample(sw, energised, now_ms - DEBOUNCE_MS));
	zassert_ok(tank_level_switch_sample(sw, energised, now_ms));
}

static struct tank_scan_sources sources(size_t n_levels, size_t n_temps, size_t n_contacts)
{
	return (struct tank_scan_sources){.levels = levels,
					  .level_count = n_levels,
					  .temperatures = temps,
					  .temperature_count = n_temps,
					  .contacts = contacts,
					  .contact_count = n_contacts};
}

static void before_each(void *fixture)
{
	ARG_UNUSED(fixture);
	for (uint8_t i = 0U; i < TANK_BOOT_ID_LEN; i++) {
		boot_id[i] = (uint8_t)(i + 1U);
	}
	zassert_ok(tank_boot_time_init(&bt, boot_id, &bt_cfg));
	for (size_t i = 0U; i < ARRAY_SIZE(levels); i++) {
		zassert_ok(tank_loop_level_init(&levels[i], &loop_cfg));
		zassert_ok(tank_product_temperature_init(&temps[i], &temp_cfg));
	}
	for (size_t i = 0U; i < ARRAY_SIZE(contacts); i++) {
		zassert_ok(tank_level_switch_init(&contacts[i], &contact_cfg));
	}
}

ZTEST_SUITE(scan_builder, NULL, NULL, before_each, NULL, NULL);

ZTEST(scan_builder, test_good_readings_are_scaled_with_header_and_age)
{
	struct tank_scan_sources src = sources(1U, 1U, 2U);

	feed_loop(&levels[0], 12.345f, false, T0 - 30U);
	feed_temp(&temps[0], R_85_DEGC, false, T0 - 20U);
	confirm_contact(&contacts[0], false, T0 - 10U); /* de-energised: asserted */
	confirm_contact(&contacts[1], true, T0 - 10U);	/* energised: clear */
	zassert_ok(tank_scan_build(&src, &bt, SL, SEQ, T0, &scan));

	zassert_mem_equal(scan.boot_id, boot_id, TANK_BOOT_ID_LEN);
	zassert_equal(scan.sl, SL);
	zassert_equal(scan.seq, SEQ);
	zassert_equal(scan.up_ms, T0);
	zassert_false(scan.tk);
	zassert_equal(scan.count, 4U);
	zassert_equal(scan.r[0].id, 1001U);
	zassert_equal(scan.r[0].val, 12345, "microamps, got %d", scan.r[0].val);
	zassert_equal(scan.r[0].age_ms, 30U);
	zassert_equal(scan.r[1].id, 2001U);
	zassert_within(scan.r[1].val, 8500, 1, "centi-degC, got %d", scan.r[1].val);
	zassert_equal(scan.r[1].age_ms, 20U);
	zassert_equal(scan.r[2].val, 1, "asserted");
	zassert_equal(scan.r[3].val, 0, "clear");
	zassert_equal(scan.r[3].age_ms, 10U);
	for (uint8_t i = 0U; i < scan.count; i++) {
		zassert_equal(scan.r[i].q, TANK_QUALITY_GOOD);
		zassert_true(scan.r[i].has_val);
	}
}

ZTEST(scan_builder, test_faults_and_never_read_inputs_carry_no_value)
{
	struct tank_scan_sources src = sources(2U, 2U, 1U);

	feed_loop(&levels[0], 12.0f, true, T0);
	feed_temp(&temps[0], R_85_DEGC, true, T0);
	/* levels[1], temps[1] and contacts[0] are never read. */
	zassert_ok(tank_scan_build(&src, &bt, SL, SEQ, T0, &scan));

	zassert_equal(scan.r[0].q, TANK_QUALITY_FAULT);
	zassert_equal(scan.r[1].q, TANK_QUALITY_UNCONFIGURED);
	zassert_equal(scan.r[2].q, TANK_QUALITY_FAULT);
	zassert_equal(scan.r[3].q, TANK_QUALITY_UNCONFIGURED);
	zassert_equal(scan.r[4].q, TANK_QUALITY_FAULT, "an unknown contact is a fault");
	for (uint8_t i = 0U; i < scan.count; i++) {
		zassert_false(scan.r[i].has_val);
		zassert_equal(scan.r[i].val, 0);
	}
}

ZTEST(scan_builder, test_out_of_range_and_stale_keep_their_value)
{
	struct tank_scan_sources src = sources(1U, 1U, 1U);

	feed_loop(&levels[0], 20.5f, false, T0);
	feed_temp(&temps[0], R_250_DEGC, false, T0);
	confirm_contact(&contacts[0], false, T0);
	zassert_ok(tank_scan_build(&src, &bt, SL, SEQ, T0, &scan));
	zassert_equal(scan.r[0].q, TANK_QUALITY_OUT_OF_RANGE);
	zassert_equal(scan.r[0].val, 20500);
	zassert_equal(scan.r[1].q, TANK_QUALITY_OUT_OF_RANGE);
	zassert_within(scan.r[1].val, 25000, 1);

	zassert_ok(tank_scan_build(&src, &bt, SL, SEQ + 1U, T0 + LATER_MS, &scan));
	for (uint8_t i = 0U; i < scan.count; i++) {
		zassert_equal(scan.r[i].q, TANK_QUALITY_STALE, "reading %u", i);
		zassert_true(scan.r[i].has_val);
		zassert_equal(scan.r[i].age_ms, LATER_MS);
	}
	zassert_equal(scan.r[2].val, 1);
}

ZTEST(scan_builder, test_time_known_after_sync_and_negative_values_round)
{
	struct tank_scan_sources src = sources(0U, 1U, 0U);

	zassert_ok(tank_boot_time_record_sync(&bt, T0, EPOCH_MS));
	feed_temp(&temps[0], 99.5177f, false, T0); /* about -1.23 degC */
	zassert_ok(tank_scan_build(&src, &bt, SL, SEQ, T0 + 2000U, &scan));
	zassert_true(scan.tk);
	zassert_equal(scan.t_s, (EPOCH_MS + 2000U) / 1000U);
	zassert_equal(scan.r[0].q, TANK_QUALITY_OUT_OF_RANGE);
	zassert_within(scan.r[0].val, -123, 1, "got %d", scan.r[0].val);
}

ZTEST(scan_builder, test_built_scan_encodes)
{
	struct tank_scan_sources src = sources(2U, 2U, 3U);
	static uint8_t buf[TANK_SCAN_MAX_ENCODED];
	struct tank_scan out;
	size_t len;

	feed_loop(&levels[0], 8.0f, false, T0);
	feed_temp(&temps[1], R_85_DEGC, false, T0);
	confirm_contact(&contacts[2], true, T0);
	zassert_ok(tank_scan_build(&src, &bt, SL, SEQ, T0, &scan));
	len = tank_scan_encode_full(&scan, buf, sizeof(buf));
	zassert_true(len > 0U);
	zassert_ok(tank_scan_decode_full(buf, len, &out));
	zassert_equal(out.count, 7U);
	zassert_equal(out.r[0].val, scan.r[0].val);
}

ZTEST(scan_builder, test_bad_arguments_are_refused)
{
	struct tank_scan_sources src = sources(1U, 0U, 0U);
	struct tank_scan_sources bad;
	struct tank_boot_time blank = {0};

	zassert_equal(tank_scan_build(NULL, &bt, SL, SEQ, T0, &scan), -EINVAL);
	zassert_equal(tank_scan_build(&src, NULL, SL, SEQ, T0, &scan), -EINVAL);
	zassert_equal(tank_scan_build(&src, &bt, SL, SEQ, T0, NULL), -EINVAL);
	zassert_equal(tank_scan_build(&src, &blank, SL, SEQ, T0, &scan), -EINVAL, "uninitialised");
	bad = sources(0U, 0U, 0U);
	zassert_equal(tank_scan_build(&bad, &bt, SL, SEQ, T0, &scan), -EINVAL, "no inputs");
	bad = sources(0U, 0U, TANK_SCAN_MAX_READINGS + 1U);
	zassert_equal(tank_scan_build(&bad, &bt, SL, SEQ, T0, &scan), -EINVAL, "too many");
	bad = sources(1U, 1U, 1U);
	bad.levels = NULL;
	zassert_equal(tank_scan_build(&bad, &bt, SL, SEQ, T0, &scan), -EINVAL);
	bad = sources(1U, 1U, 1U);
	bad.temperatures = NULL;
	zassert_equal(tank_scan_build(&bad, &bt, SL, SEQ, T0, &scan), -EINVAL);
	bad = sources(1U, 1U, 1U);
	bad.contacts = NULL;
	zassert_equal(tank_scan_build(&bad, &bt, SL, SEQ, T0, &scan), -EINVAL);
	bad = sources(0U, 0U, TANK_SCAN_MAX_READINGS);
	zassert_ok(tank_scan_build(&bad, &bt, SL, SEQ, T0, &scan), "exactly the maximum");
	zassert_equal(scan.count, TANK_SCAN_MAX_READINGS);
}
