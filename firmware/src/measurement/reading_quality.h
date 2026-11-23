/*
 * The quality flag every reading carries.
 *
 * ADR-0008: every value carries a quality flag and an age. The enumerators and
 * their numeric values mirror `quality-values` in interfaces/records.cddl
 * exactly, because the record layer sends this number on the wire and the
 * cloud and the dashboard read it. Changing a value here changes the contract
 * and needs a records.cddl change, not a firmware change.
 *
 * What the record carries alongside each flag (records.cddl `reading`):
 *   good, out-of-range, stale  a value is sent;
 *   fault, unconfigured        no value is sent, because there is no
 *                              trustworthy number and a failed sensor is
 *                              flagged and excluded, never silently replaced
 *                              (AGENTS.md section 7).
 *
 * Only `good` may be shown as a live measurement.
 */

#ifndef TANK_MEASUREMENT_READING_QUALITY_H_
#define TANK_MEASUREMENT_READING_QUALITY_H_

enum tank_reading_quality {
	/* Sampled normally, inside the valid range. */
	TANK_QUALITY_GOOD = 0,
	/* Last known value, not refreshed this scan. */
	TANK_QUALITY_STALE = 1,
	/* Sampled, but outside the signal's valid range. */
	TANK_QUALITY_OUT_OF_RANGE = 2,
	/* Sensor or bus failure; no value is sent. */
	TANK_QUALITY_FAULT = 3,
	/* Channel present in hardware but not commissioned; no value is sent. */
	TANK_QUALITY_UNCONFIGURED = 4,
};

#endif /* TANK_MEASUREMENT_READING_QUALITY_H_ */
