/*
 * PT100 linearisation: resistance to temperature, Callendar-Van Dusen.
 *
 * Story S-032 (P1-06). Measurement layer (ADR-0003: hardware, measurement,
 * record, communications). The hardware layer hands over a resistance in ohms
 * (see src/hardware/max31865.h); this module turns it into degrees Celsius.
 *
 * IEC 60751 gives, for t >= 0 degC:
 *
 *     R(t) = R0 * (1 + A*t + B*t^2)
 *
 * which inverts exactly, with no iteration and no lookup table:
 *
 *     t = (-A + sqrt(A^2 - 4*B*(1 - R/R0))) / (2*B)
 *
 * Below 0 degC the standard adds a third term, C*(t - 100)*t^3, and the
 * quadratic above is no longer the right model. The product operating range is
 * 0 to 200 degC (tech lead, 23 Nov 2026), so a sub-zero reading is outside the
 * range the signal list declares and is flagged out of range and excluded by
 * the caller. This module still returns the quadratic's answer there rather
 * than refusing, so the caller can report how far out of range a reading sits
 * instead of hiding it, the same choice scaling.c makes for the 4-20 mA
 * inputs. That answer drifts from the standard the further below zero it goes
 * and must not be treated as a measurement.
 *
 * The sensor class (Class B, provisional, AGENTS.md section 5) does not appear
 * here: it sets the accuracy budget, verified at bench by P1-25, not the
 * conversion. A Class A sensor follows the same curve.
 */

#ifndef TANK_MEASUREMENT_PT100_H_
#define TANK_MEASUREMENT_PT100_H_

/* Nominal resistance at 0 degC, the 100 in "PT100" (IEC 60751). */
#define TANK_PT100_R0_OHMS 100.0f

/*
 * Convert an RTD resistance in ohms to degrees Celsius and store it in
 * out_degc.
 *
 * Returns 0 on success, -EINVAL if out_degc is NULL or resistance_ohms is not
 * positive, or -ERANGE if the resistance is above the curve's turning point
 * (about 761 ohms, far beyond any PT100), where the inverse has no real
 * solution. On failure out_degc is left untouched.
 */
int tank_pt100_temperature(float resistance_ohms, float *out_degc);

#endif /* TANK_MEASUREMENT_PT100_H_ */
