/*
 * ztest suite for the AD4111 data and status decode (S-034, P1-04).
 *
 * The chip is simulated at the byte level: these frames are what the SPI read
 * would return in each condition. Full scale is 25 mA here only as this
 * test's fixture value ([Confirm] with the EE); the module takes it as a
 * parameter.
 */

#include <zephyr/ztest.h>

#include <errno.h>
#include <stddef.h>

#include "ad4111.h"

#define FULL_SCALE_MA 25.0f
#define TOLERANCE_MA 0.001f
#define STATUS_OK_CH1 0x01U
#define STATUS_OK_CH2 0x02U

/* code24 = round(current / full_scale * 2^24); 12 mA is 0.48 of full scale. */
static void decode_code(uint32_t code24, uint8_t status, struct tank_ad4111_reading *out)
{
	const uint8_t data[3] = {(uint8_t)(code24 >> 16), (uint8_t)(code24 >> 8), (uint8_t)code24};

	zassert_equal(tank_ad4111_decode(data, status, FULL_SCALE_MA, out), 0, "decode failed");
}

ZTEST_SUITE(hardware_ad4111, NULL, NULL, NULL, NULL, NULL);

ZTEST(hardware_ad4111, test_nominal_codes_decode_to_the_expected_current)
{
	struct tank_ad4111_reading r = {0};

	decode_code(0x000000U, STATUS_OK_CH1, &r);
	zassert_within(r.current_ma, 0.0f, TOLERANCE_MA);

	decode_code(0x7AE148U, STATUS_OK_CH1, &r); /* 12 mA */
	zassert_within(r.current_ma, 12.0f, TOLERANCE_MA);
	zassert_equal(r.raw_code24, 0x7AE148U);
	zassert_true(tank_ad4111_reading_ok(&r));

	decode_code(0xCCCCCDU, STATUS_OK_CH1, &r); /* 20 mA */
	zassert_within(r.current_ma, 20.0f, TOLERANCE_MA);

	decode_code(0xFFFFFFU, STATUS_OK_CH1, &r);
	zassert_within(r.current_ma, 25.0f, TOLERANCE_MA);
}

ZTEST(hardware_ad4111, test_the_channel_comes_from_the_status_byte)
{
	struct tank_ad4111_reading r = {0};

	decode_code(0x7AE148U, STATUS_OK_CH1, &r);
	zassert_equal(r.channel, 1U);
	decode_code(0x7AE148U, STATUS_OK_CH2, &r);
	zassert_equal(r.channel, 2U);
}

ZTEST(hardware_ad4111, test_each_status_flag_is_decoded_and_makes_the_reading_not_ok)
{
	struct tank_ad4111_reading r = {0};

	decode_code(0x7AE148U, STATUS_OK_CH1 | TANK_AD4111_STATUS_NOT_READY, &r);
	zassert_true(r.not_ready);
	zassert_false(tank_ad4111_reading_ok(&r));

	decode_code(0x7AE148U, STATUS_OK_CH1 | TANK_AD4111_STATUS_ADC_ERROR, &r);
	zassert_true(r.adc_error);
	zassert_false(tank_ad4111_reading_ok(&r));

	decode_code(0x7AE148U, STATUS_OK_CH1 | TANK_AD4111_STATUS_CRC_ERROR, &r);
	zassert_true(r.crc_error);
	zassert_false(tank_ad4111_reading_ok(&r));

	decode_code(0x7AE148U, STATUS_OK_CH1 | TANK_AD4111_STATUS_REG_ERROR, &r);
	zassert_true(r.reg_error);
	zassert_false(tank_ad4111_reading_ok(&r));
}

ZTEST(hardware_ad4111, test_a_clean_status_leaves_every_flag_clear)
{
	struct tank_ad4111_reading r = {0};

	decode_code(0x7AE148U, STATUS_OK_CH1, &r);
	zassert_false(r.not_ready);
	zassert_false(r.adc_error);
	zassert_false(r.crc_error);
	zassert_false(r.reg_error);
}

ZTEST(hardware_ad4111, test_bad_arguments_are_rejected_and_leave_out_untouched)
{
	struct tank_ad4111_reading r = {.raw_code24 = 77U};
	const uint8_t data[3] = {0x12, 0x34, 0x56};

	zassert_equal(tank_ad4111_decode(NULL, 0U, FULL_SCALE_MA, &r), -EINVAL);
	zassert_equal(tank_ad4111_decode(data, 0U, FULL_SCALE_MA, NULL), -EINVAL);
	zassert_equal(tank_ad4111_decode(data, 0U, 0.0f, &r), -EINVAL);
	zassert_equal(tank_ad4111_decode(data, 0U, -1.0f, &r), -EINVAL);
	zassert_equal(r.raw_code24, 77U);
	zassert_false(tank_ad4111_reading_ok(NULL));
}
