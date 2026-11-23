/* The 4-20 mA level reads and their quality flags. See loop_level.h. */

#include "loop_level.h"

#include <errno.h>
#include <stddef.h>

/* Wrap-safe elapsed time between two free-running millisecond counts. */
static uint32_t elapsed_ms(uint32_t now_ms, uint32_t since_ms)
{
	return (uint32_t)(now_ms - since_ms);
}

static bool current_is_failure(float current_ma)
{
	return (current_ma < TANK_LOOP_LEVEL_FAULT_LOW_MA) ||
	       (current_ma > TANK_LOOP_LEVEL_FAULT_HIGH_MA);
}

uint32_t tank_loop_level_live_window_ms(const struct tank_loop_level_config *config)
{
	if (config == NULL) {
		return 0;
	}

	return config->update_rate_ms * (1U + TANK_LOOP_LEVEL_MISSED_UPDATES_ALLOWED);
}

int tank_loop_level_init(struct tank_loop_level *level, const struct tank_loop_level_config *config)
{
	if ((level == NULL) || (config == NULL)) {
		return -EINVAL;
	}

	if ((config->channel < TANK_AD4111_CHANNEL_MIN) ||
	    (config->channel > TANK_AD4111_CHANNEL_MAX) || (config->update_rate_ms == 0U) ||
	    !(config->valid_low_ma < config->valid_high_ma)) {
		return -EINVAL;
	}

	level->config = *config;
	level->quality = TANK_QUALITY_UNCONFIGURED;
	level->current_ma = 0.0f;
	level->sampled_at_ms = 0U;
	level->have_reading = false;

	return 0;
}

int tank_loop_level_update(struct tank_loop_level *level, const struct tank_ad4111_reading *reading,
			   uint32_t now_ms)
{
	if ((level == NULL) || (reading == NULL) || (level->config.update_rate_ms == 0U) ||
	    (reading->channel != level->config.channel)) {
		return -EINVAL;
	}

	if (!tank_ad4111_reading_ok(reading) || current_is_failure(reading->current_ma)) {
		level->quality = TANK_QUALITY_FAULT;
		level->current_ma = 0.0f;
	} else {
		const bool in_range = (reading->current_ma >= level->config.valid_low_ma) &&
				      (reading->current_ma <= level->config.valid_high_ma);

		level->quality = in_range ? TANK_QUALITY_GOOD : TANK_QUALITY_OUT_OF_RANGE;
		level->current_ma = reading->current_ma;
	}

	level->sampled_at_ms = now_ms;
	level->have_reading = true;

	return 0;
}

int tank_loop_level_status(const struct tank_loop_level *level, uint32_t now_ms,
			   struct tank_loop_level_status *out)
{
	if ((level == NULL) || (out == NULL)) {
		return -EINVAL;
	}

	out->signal_id = level->config.signal_id;

	if (!level->have_reading) {
		out->quality = TANK_QUALITY_UNCONFIGURED;
		out->current_ma = 0.0f;
		out->live = false;
		out->age_ms = 0U;
		return 0;
	}

	enum tank_reading_quality quality = level->quality;
	const uint32_t age_ms = elapsed_ms(now_ms, level->sampled_at_ms);

	/* A fault stays a fault: the channel is broken, not out of date. */
	if (((quality == TANK_QUALITY_GOOD) || (quality == TANK_QUALITY_OUT_OF_RANGE)) &&
	    (age_ms > tank_loop_level_live_window_ms(&level->config))) {
		quality = TANK_QUALITY_STALE;
	}

	out->quality = quality;
	out->current_ma = (quality == TANK_QUALITY_FAULT) ? 0.0f : level->current_ma;
	out->live = (quality == TANK_QUALITY_GOOD);
	out->age_ms = age_ms;

	return 0;
}
