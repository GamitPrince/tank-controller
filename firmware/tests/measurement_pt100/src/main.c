/*
 * ztest suite for the PT100 Callendar-Van Dusen linearisation (S-032, P1-06).
 *
 * Reference resistances come from IEC 60751's own R(t) polynomial, not from
 * this module's inverse, so the test does not just check the inverse against
 * itself. The tolerance is far tighter than the P1-06 accuracy target
 * (+/-2.0 degC): linearisation must spend almost none of that budget, leaving
 * it for the sensor and the measurement chain, which only the bench test
 * (P1-25) can check.
 */

#include <zephyr/ztest.h>

#include <errno.h>

#include "pt100.h"

#define TOLERANCE_DEGC 0.01f

static float temperature_or_fail(float resistance_ohms)
{
	float degc = 0.0f;
	const int err = tank_pt100_temperature(resistance_ohms, &degc);

	zassert_equal(err, 0, "linearising a positive resistance should succeed, got %d", err);
	return degc;
}

ZTEST_SUITE(measurement_pt100, NULL, NULL, NULL, NULL, NULL);

ZTEST(measurement_pt100, test_reference_resistances_across_the_operating_range)
{
	/* IEC 60751 R(t) for a PT100 (R0 = 100 ohms) at 0, 25, 50, 100, 150, 200 degC. */
	zassert_within(temperature_or_fail(100.0000f), 0.0f, TOLERANCE_DEGC);
	zassert_within(temperature_or_fail(109.7347f), 25.0f, TOLERANCE_DEGC);
	zassert_within(temperature_or_fail(119.3971f), 50.0f, TOLERANCE_DEGC);
	zassert_within(temperature_or_fail(138.5055f), 100.0f, TOLERANCE_DEGC);
	zassert_within(temperature_or_fail(157.3251f), 150.0f, TOLERANCE_DEGC);
	zassert_within(temperature_or_fail(175.8560f), 200.0f, TOLERANCE_DEGC);
}

ZTEST(measurement_pt100, test_a_resistance_above_the_operating_range_still_linearises)
{
	/* 266 degC worth of resistance: outside the 0-200 degC range, but the
	 * curve is still defined there. The caller, not this module, decides
	 * that it is out of range.
	 */
	zassert_within(temperature_or_fail(200.0000f), 266.35f, 0.1f);
}

ZTEST(measurement_pt100, test_a_resistance_below_zero_degc_still_returns_an_answer)
{
	/* Below 0 degC the IEC 60751 polynomial gains a cubic term this module
	 * does not implement, so the quadratic's answer drifts from the
	 * standard. The product operating range is 0-200 degC, so this result
	 * is only ever seen as an out-of-range reading, never as a measurement.
	 */
	float degc = 0.0f;

	zassert_equal(tank_pt100_temperature(80.0f, &degc), 0);
	zassert_true(degc < 0.0f, "80 ohms is below the R0 of 100 ohms at 0 degC");
}

ZTEST(measurement_pt100, test_rejects_non_positive_resistance)
{
	float degc = 0.0f;

	zassert_equal(tank_pt100_temperature(0.0f, &degc), -EINVAL);
	zassert_equal(tank_pt100_temperature(-10.0f, &degc), -EINVAL);
}

ZTEST(measurement_pt100, test_rejects_null_output)
{
	zassert_equal(tank_pt100_temperature(100.0f, NULL), -EINVAL);
}

ZTEST(measurement_pt100, test_rejects_a_resistance_beyond_the_curves_turning_point)
{
	float degc = 0.0f;

	/* Far beyond any real PT100; the inverse has no real solution there. */
	zassert_equal(tank_pt100_temperature(10000.0f, &degc), -ERANGE);
}
