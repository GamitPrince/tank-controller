/*
 * Linear scaling between a raw transducer reading and an engineering value.
 *
 * Measurement layer (ADR-0003: hardware, measurement, record, communications).
 * Used for the 4-20 mA inputs on the AD4111 (ADR-0002: channel 1 radar level,
 * channel 2 pressure level). The spans come from the signal list in
 * interfaces/ once story P1-03 defines it; nothing is hardcoded here.
 *
 * A reading outside the raw span is reported as out of range rather than
 * clamped. AGENTS.md section 7 requires a failed or out-of-range sensor to be
 * flagged and excluded, never silently replaced, so the caller decides.
 */

#ifndef TANK_MEASUREMENT_SCALING_H_
#define TANK_MEASUREMENT_SCALING_H_

#include <stdbool.h>

/* A scaled value and whether its raw input sat inside the raw span. */
struct tank_scaled_reading {
	float value;
	bool in_range;
};

/*
 * Map raw from [raw_low, raw_high] onto [eng_low, eng_high] and store the
 * result in out.
 *
 * The value is extrapolated beyond the raw span rather than clamped, so a
 * caller can see how far out of range a reading is. out->in_range reports
 * whether raw was inside the span, inclusive of both ends.
 *
 * Returns 0 on success, -EINVAL if either span is zero or inverted, or if out
 * is NULL. On failure out is left untouched.
 */
int tank_scale_linear(float raw, float raw_low, float raw_high, float eng_low, float eng_high,
		      struct tank_scaled_reading *out);

#endif /* TANK_MEASUREMENT_SCALING_H_ */
