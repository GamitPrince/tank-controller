/*
 * ztest suite for the MAX31865 register decode (S-032, P1-06).
 *
 * The chip is simulated at the register level: these raw bytes are exactly
 * what tank_max31865_decode() would read over SPI from a real chip in each
 * condition, not a stand-in for the chip's internal behaviour. Rref is 400
 * ohms throughout, the EE's recommended low-tempco reference (P1-06 open
 * question); the firmware does not hardcode it, so this is only this test's
 * fixture value.
 */

#include <zephyr/ztest.h>

#include <errno.h>

#include "max31865.h"

#define RREF_OHMS 400.0f
#define TOLERANCE_OHMS 0.05f

/* code15 = round(resistance / rref * 32768); raw16 = (code15 << 1) | fault_bit. */
static void decode_or_fail(uint16_t code15, bool fault_bit, uint8_t fault_status,
			   struct tank_max31865_reading *out)
{
	const uint16_t raw16 = (uint16_t)(code15 << 1) | (fault_bit ? 1U : 0U);
	const uint8_t msb = (uint8_t)(raw16 >> 8);
	const uint8_t lsb = (uint8_t)(raw16 & 0xFFU);

	zassert_equal(tank_max31865_decode(msb, lsb, fault_status, RREF_OHMS, out), 0,
		      "decode failed");
}

ZTEST_SUITE(hardware_max31865, NULL, NULL, NULL, NULL, NULL);

ZTEST(hardware_max31865, test_nominal_codes_decode_to_the_expected_resistance)
{
	struct tank_max31865_reading reading = {0};

	/* 0, 25, 100 and 200 degC on a PT100 (IEC 60751), Rref 400 ohms. */
	decode_or_fail(8192U, false, 0U, &reading);
	zassert_within(reading.resistance_ohms, 100.0f, TOLERANCE_OHMS);
	zassert_false(reading.fault_bit);
	zassert_equal(reading.fault_flags, 0U);

	decode_or_fail(8989U, false, 0U, &reading);
	zassert_within(reading.resistance_ohms, 109.7347f, TOLERANCE_OHMS);

	decode_or_fail(11346U, false, 0U, &reading);
	zassert_within(reading.resistance_ohms, 138.5055f, TOLERANCE_OHMS);

	decode_or_fail(14406U, false, 0U, &reading);
	zassert_within(reading.resistance_ohms, 175.8560f, TOLERANCE_OHMS);
}

ZTEST(hardware_max31865, test_an_open_circuit_saturates_near_full_scale)
{
	struct tank_max31865_reading reading = {0};

	decode_or_fail(32100U, true, TANK_MAX31865_FAULT_RTDIN_LOW_OPEN, &reading);

	zassert_true(reading.fault_bit, "an open RTD must set the register's own fault bit");
	zassert_true(tank_max31865_reading_is_open(&reading), "a near-full-scale code is open");
	zassert_false(tank_max31865_reading_is_short(&reading), "open and short are exclusive");
}

ZTEST(hardware_max31865, test_a_short_reads_near_zero)
{
	struct tank_max31865_reading reading = {0};

	decode_or_fail(5U, false, 0U, &reading);

	zassert_true(tank_max31865_reading_is_short(&reading), "a near-zero code is a short");
	zassert_false(tank_max31865_reading_is_open(&reading), "open and short are exclusive");
}

ZTEST(hardware_max31865, test_the_fault_status_register_is_decoded_even_without_the_fault_bit)
{
	struct tank_max31865_reading reading = {0};

	/* A healthy-looking code, but the fault register still flags a threshold crossing. */
	decode_or_fail(8192U, false, TANK_MAX31865_FAULT_RTD_HIGH_THRESHOLD, &reading);

	zassert_equal(reading.fault_flags, TANK_MAX31865_FAULT_RTD_HIGH_THRESHOLD);
	zassert_false(tank_max31865_reading_is_open(&reading),
		      "a threshold flag alone is not an open-circuit flag");
	zassert_false(tank_max31865_reading_is_short(&reading));
}

ZTEST(hardware_max31865, test_refin_open_flag_is_recognised_as_open)
{
	struct tank_max31865_reading reading = {0};

	decode_or_fail(8192U, true, TANK_MAX31865_FAULT_REFIN_LOW_OPEN, &reading);

	zassert_true(tank_max31865_reading_is_open(&reading));
}

ZTEST(hardware_max31865, test_invalid_arguments_are_refused)
{
	struct tank_max31865_reading reading = {0};

	zassert_equal(tank_max31865_decode(0x40U, 0x00U, 0U, RREF_OHMS, NULL), -EINVAL,
		      "a NULL output pointer must be rejected");
	zassert_equal(tank_max31865_decode(0x40U, 0x00U, 0U, 0.0f, &reading), -EINVAL,
		      "a zero reference resistor must be rejected");
	zassert_equal(tank_max31865_decode(0x40U, 0x00U, 0U, -400.0f, &reading), -EINVAL,
		      "a negative reference resistor must be rejected");
}

ZTEST(hardware_max31865, test_null_reading_pointers_are_refused_by_the_classifiers)
{
	zassert_false(tank_max31865_reading_is_open(NULL));
	zassert_false(tank_max31865_reading_is_short(NULL));
}
