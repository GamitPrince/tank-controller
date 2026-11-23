/* The six product temperature reads and their quality flags. See product_temperature.h. */

#include "product_temperature.h"

#include <errno.h>

#include "pt100.h"

/* Wrap-safe elapsed time between two free-running millisecond counts. */
static uint32_t elapsed_ms(uint32_t now_ms, uint32_t since_ms)
{
	return (uint32_t)(now_ms - since_ms);
}

static bool level_is_known(enum tank_product_level level)
{
	return (level == TANK_PRODUCT_LEVEL_UPPER) || (level == TANK_PRODUCT_LEVEL_MIDDLE) ||
	       (level == TANK_PRODUCT_LEVEL_BOTTOM);
}

/*
 * Whether the chip is telling us not to trust this reading.
 *
 * Any set fault flag counts, even when the chip's own fault bit is clear: a
 * fault register still showing an open RTD, a short, a threshold crossing or
 * an over-voltage is reason enough to withhold the value. Reporting a fault
 * that has just cleared costs one update period, while reporting a bad
 * temperature as live is the failure AGENTS.md section 7 forbids. The ADC code
 * is checked too, so a saturated or dead channel is caught even if the fault
 * register was never read.
 */
static bool reading_is_faulty(const struct tank_max31865_reading *reading)
{
	return reading->fault_bit || (reading->fault_flags != 0U) ||
	       tank_max31865_reading_is_open(reading) || tank_max31865_reading_is_short(reading);
}

uint32_t
tank_product_temperature_live_window_ms(const struct tank_product_temperature_config *config)
{
	if (config == NULL) {
		return 0;
	}

	return config->update_rate_ms * (1U + TANK_PRODUCT_TEMPERATURE_MISSED_UPDATES_ALLOWED);
}

uint32_t
tank_product_temperature_fault_deadline_ms(const struct tank_product_temperature_config *config)
{
	if (config == NULL) {
		return 0;
	}

	return config->update_rate_ms;
}

int tank_product_temperature_init(struct tank_product_temperature *sensor,
				  const struct tank_product_temperature_config *config)
{
	if ((sensor == NULL) || (config == NULL)) {
		return -EINVAL;
	}

	if ((config->chip_select < TANK_MAX31865_CHIP_SELECT_MIN) ||
	    (config->chip_select > TANK_MAX31865_CHIP_SELECT_MAX)) {
		return -EINVAL;
	}

	if (!level_is_known(config->level) || (config->update_rate_ms == 0U) ||
	    !(config->valid_low_degc < config->valid_high_degc)) {
		return -EINVAL;
	}

	sensor->config = *config;
	sensor->quality = TANK_QUALITY_UNCONFIGURED;
	sensor->temperature_degc = 0.0f;
	sensor->sampled_at_ms = 0U;
	sensor->have_reading = false;

	return 0;
}

int tank_product_temperature_update(struct tank_product_temperature *sensor,
				    const struct tank_max31865_reading *reading, uint32_t now_ms)
{
	if ((sensor == NULL) || (reading == NULL) || (sensor->config.update_rate_ms == 0U)) {
		return -EINVAL;
	}

	float temperature_degc = 0.0f;

	if (reading_is_faulty(reading) ||
	    (tank_pt100_temperature(reading->resistance_ohms, &temperature_degc) != 0)) {
		sensor->quality = TANK_QUALITY_FAULT;
		sensor->temperature_degc = 0.0f;
	} else {
		const bool in_range = (temperature_degc >= sensor->config.valid_low_degc) &&
				      (temperature_degc <= sensor->config.valid_high_degc);

		sensor->quality = in_range ? TANK_QUALITY_GOOD : TANK_QUALITY_OUT_OF_RANGE;
		sensor->temperature_degc = temperature_degc;
	}

	sensor->sampled_at_ms = now_ms;
	sensor->have_reading = true;

	return 0;
}

int tank_product_temperature_status(const struct tank_product_temperature *sensor, uint32_t now_ms,
				    struct tank_product_temperature_status *out)
{
	if ((sensor == NULL) || (out == NULL)) {
		return -EINVAL;
	}

	out->signal_id = sensor->config.signal_id;

	if (!sensor->have_reading) {
		out->quality = TANK_QUALITY_UNCONFIGURED;
		out->temperature_degc = 0.0f;
		out->live = false;
		out->age_ms = 0U;
		return 0;
	}

	enum tank_reading_quality quality = sensor->quality;
	const uint32_t age_ms = elapsed_ms(now_ms, sensor->sampled_at_ms);

	/*
	 * A reading that has stopped being refreshed is reported stale whatever
	 * it said, so it is never presented as current. A fault stays a fault:
	 * the sensor is broken, not out of date, and it carries no value to go
	 * stale in the first place.
	 */
	if (((quality == TANK_QUALITY_GOOD) || (quality == TANK_QUALITY_OUT_OF_RANGE)) &&
	    (age_ms > tank_product_temperature_live_window_ms(&sensor->config))) {
		quality = TANK_QUALITY_STALE;
	}

	out->quality = quality;
	out->temperature_degc = (quality == TANK_QUALITY_FAULT) ? 0.0f : sensor->temperature_degc;
	out->live = (quality == TANK_QUALITY_GOOD);
	out->age_ms = age_ms;

	return 0;
}
