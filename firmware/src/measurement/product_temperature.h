/*
 * The six product temperature reads, each with its own quality flag.
 *
 * Story S-032 (P1-06). ADR-0002: six 3-wire PT100s on one MAX31865, a separate
 * chip select per channel with common SCK, MOSI and MISO. Two sensors per
 * mounting level, 180 degrees apart across the tank diameter. The signal list
 * in interfaces/ owns the ids, chip selects, positions, update rates and valid
 * ranges, and firmware/scripts/gen_temperature_signals.py turns them into the
 * generated table this module serves (see product_temperature_config.c).
 *
 * Each sensor is read and reported independently. **Comparing the two sensors
 * of a pair is Phase 2** (stratification and sensor-mismatch checks), so
 * nothing here averages, cross-checks or substitutes one sensor for another.
 * A failed sensor is flagged and excluded; the other five keep reporting.
 *
 * Phase 1 is read-only monitoring. This module takes readings and hands back a
 * status; it has no way to drive a heater, a valve or any output, and must not
 * gain one.
 *
 * Quality, in the words of interfaces/records.cddl (see reading_quality.h):
 *   - a chip fault bit, an open circuit or a short is `fault`, and no
 *     temperature is reported: a failed sensor is never silently replaced;
 *   - a reading outside the signal's valid range is `out-of-range`, and the
 *     temperature is still reported so a consumer can see how far out it sits;
 *   - a reading that is no longer being refreshed becomes `stale`, so stale
 *     data is never shown as live (AGENTS.md section 7);
 *   - a sensor that has not been read yet is `unconfigured`. The schema has no
 *     "never sampled" flag, and `unconfigured` is its only value that means
 *     "no trustworthy number, and not a sensor failure", so it is the honest
 *     one to report before the first reading arrives.
 * Only `good` may be shown as a live measurement.
 */

#ifndef TANK_MEASUREMENT_PRODUCT_TEMPERATURE_H_
#define TANK_MEASUREMENT_PRODUCT_TEMPERATURE_H_

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "max31865.h"
#include "reading_quality.h"

/* Where a sensor is mounted up the tank: its height, not the tank's fill level. */
enum tank_product_level {
	TANK_PRODUCT_LEVEL_UPPER = 0,
	TANK_PRODUCT_LEVEL_MIDDLE = 1,
	TANK_PRODUCT_LEVEL_BOTTOM = 2,
};

/*
 * How many update periods a reading may go unrefreshed before it is reported
 * stale, expressed as the update rate plus the updates that may be missed.
 * At the signal list's 1000 ms update rate that is four seconds.
 *
 * [Confirm] the number of missed updates tolerated is a firmware choice, not
 * an EE figure: three leaves room for a single slow scan without declaring a
 * healthy sensor stale, and keeps the window far inside both the five-second
 * NFR-01 budget and the 60-second fault deadline below.
 */
#define TANK_PRODUCT_TEMPERATURE_MISSED_UPDATES_ALLOWED 3U

/*
 * P1-06 requires a broken or shorted RTD to be flagged within 60 seconds.
 * A fault is in fact flagged by the reading that shows it, so the real latency
 * is one update period; this is the acceptance criterion's ceiling, which
 * tank_product_temperature_fault_deadline_ms() is checked against.
 */
#define TANK_PRODUCT_TEMPERATURE_FAULT_DEADLINE_MS 60000U

/* One sensor's contract, taken from the signal list. Read-only by nature. */
struct tank_product_temperature_config {
	/* Signal id the record carries for this sensor. */
	uint16_t signal_id;
	/* The sensor's own chip select on the shared SPI bus, 1 to 6. */
	uint8_t chip_select;
	enum tank_product_level level;
	/* 0 or 180 degrees: which side of the tank diameter the sensor is on. */
	uint16_t orientation_deg;
	uint32_t update_rate_ms;
	float valid_low_degc;
	float valid_high_degc;
};

/* One sensor's reading state. Treat the fields as private. */
struct tank_product_temperature {
	struct tank_product_temperature_config config;
	enum tank_reading_quality quality;
	float temperature_degc;
	uint32_t sampled_at_ms;
	bool have_reading;
};

/* What a caller may report for a sensor. */
struct tank_product_temperature_status {
	uint16_t signal_id;
	enum tank_reading_quality quality;
	/*
	 * Temperature in degrees Celsius. Meaningless, and not to be reported,
	 * when quality is fault or unconfigured.
	 */
	float temperature_degc;
	/* True only when quality is good: safe to show as a live measurement. */
	bool live;
	/* Milliseconds since the reading this status reports was taken. */
	uint32_t age_ms;
};

/*
 * Prepare sensor to read the channel described by config.
 *
 * Returns 0 on success, or -EINVAL if either pointer is NULL, the chip select
 * is outside 1 to 6, the mounting level is not a known enumerator,
 * update_rate_ms is zero, or the valid range is empty or inverted. On failure
 * sensor is left untouched.
 */
int tank_product_temperature_init(struct tank_product_temperature *sensor,
				  const struct tank_product_temperature_config *config);

/*
 * Take one decoded MAX31865 reading for this sensor, sampled at now_ms.
 *
 * reading comes from tank_max31865_decode() for this sensor's chip select.
 * now_ms is a free-running millisecond count; differences are computed so that
 * wrap-around is harmless.
 *
 * Returns 0 on success, or -EINVAL if either pointer is NULL or sensor was not
 * initialised.
 */
int tank_product_temperature_update(struct tank_product_temperature *sensor,
				    const struct tank_max31865_reading *reading, uint32_t now_ms);

/*
 * Report the sensor's reading as of now_ms into out.
 *
 * Returns 0 on success, or -EINVAL if either pointer is NULL.
 */
int tank_product_temperature_status(const struct tank_product_temperature *sensor, uint32_t now_ms,
				    struct tank_product_temperature_status *out);

/* How long a reading of this sensor stays live without a fresh reading. */
uint32_t
tank_product_temperature_live_window_ms(const struct tank_product_temperature_config *config);

/*
 * How long this sensor can take to report a broken or shorted RTD: one update
 * period, since the reading that shows the fault flags it.
 */
uint32_t
tank_product_temperature_fault_deadline_ms(const struct tank_product_temperature_config *config);

/* How many sensors story P1-06 reads, as the signal list defines them. */
size_t tank_product_temperature_config_count(void);

/* The index-th sensor contract, or NULL if index is out of range. */
const struct tank_product_temperature_config *tank_product_temperature_config_at(size_t index);

/* The contract for signal_id, or NULL if this story does not read it. */
const struct tank_product_temperature_config *
tank_product_temperature_config_by_id(uint16_t signal_id);

/* The contract for chip_select, or NULL if no sensor of this story uses it. */
const struct tank_product_temperature_config *
tank_product_temperature_config_by_chip_select(uint8_t chip_select);

#endif /* TANK_MEASUREMENT_PRODUCT_TEMPERATURE_H_ */
