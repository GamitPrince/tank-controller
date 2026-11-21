/*
 * ztest suite for the measurement layer's linear scaling.
 *
 * Covers what AGENTS.md section 7 requires: out-of-range values and invalid
 * configuration, not only the happy path.
 */

#include <zephyr/ztest.h>

#include <errno.h>

#include "scaling.h"

/* A 4-20 mA input mapped onto a 0-100 percent level, as the AD4111 channels are. */
#define RAW_LOW 4.0f
#define RAW_HIGH 20.0f
#define ENG_LOW 0.0f
#define ENG_HIGH 100.0f

#define TOLERANCE 0.001f

static struct tank_scaled_reading scale_or_fail(float raw)
{
	struct tank_scaled_reading reading = {0};
	const int err = tank_scale_linear(raw, RAW_LOW, RAW_HIGH, ENG_LOW, ENG_HIGH, &reading);

	zassert_equal(err, 0, "scaling a valid span should succeed, got %d", err);
	return reading;
}

ZTEST_SUITE(measurement_scaling, NULL, NULL, NULL, NULL, NULL);

ZTEST(measurement_scaling, test_scales_span_ends_and_midpoint)
{
	zassert_within(scale_or_fail(RAW_LOW).value, ENG_LOW, TOLERANCE);
	zassert_within(scale_or_fail(12.0f).value, 50.0f, TOLERANCE);
	zassert_within(scale_or_fail(RAW_HIGH).value, ENG_HIGH, TOLERANCE);
	zassert_within(scale_or_fail(8.0f).value, 25.0f, TOLERANCE);
}

ZTEST(measurement_scaling, test_span_ends_count_as_in_range)
{
	zassert_true(scale_or_fail(RAW_LOW).in_range);
	zassert_true(scale_or_fail(RAW_HIGH).in_range);
	zassert_true(scale_or_fail(12.0f).in_range);
}

ZTEST(measurement_scaling, test_flags_out_of_range_without_clamping)
{
	const struct tank_scaled_reading below = scale_or_fail(2.0f);
	const struct tank_scaled_reading above = scale_or_fail(22.0f);

	zassert_false(below.in_range, "a reading under the span is out of range");
	zassert_false(above.in_range, "a reading over the span is out of range");

	/* Extrapolated, not clamped, so the caller can see how far out it is. */
	zassert_within(below.value, -12.5f, TOLERANCE);
	zassert_within(above.value, 112.5f, TOLERANCE);
}

ZTEST(measurement_scaling, test_rejects_inverted_and_zero_raw_span)
{
	struct tank_scaled_reading reading = {0};

	zassert_equal(tank_scale_linear(10.0f, RAW_HIGH, RAW_LOW, ENG_LOW, ENG_HIGH, &reading),
		      -EINVAL, "an inverted raw span must be rejected");
	zassert_equal(tank_scale_linear(10.0f, RAW_LOW, RAW_LOW, ENG_LOW, ENG_HIGH, &reading),
		      -EINVAL, "a zero-width raw span must be rejected");
}

ZTEST(measurement_scaling, test_rejects_bad_engineering_span)
{
	struct tank_scaled_reading reading = {0};

	zassert_equal(tank_scale_linear(10.0f, RAW_LOW, RAW_HIGH, ENG_HIGH, ENG_LOW, &reading),
		      -EINVAL, "an inverted engineering span must be rejected");
}

ZTEST(measurement_scaling, test_rejects_null_output)
{
	zassert_equal(tank_scale_linear(10.0f, RAW_LOW, RAW_HIGH, ENG_LOW, ENG_HIGH, NULL), -EINVAL,
		      "a NULL output pointer must be rejected");
}
