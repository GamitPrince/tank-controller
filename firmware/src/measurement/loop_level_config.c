/*
 * The 4-20 mA level contracts, taken from the signal list at build time.
 *
 * tank_level_signals.h is generated from interfaces/signals-v1.yaml by
 * firmware/scripts/gen_level_signals.py and is never committed, so no signal
 * id, channel, update rate or valid range is written into C.
 */

#include "loop_level.h"

#include <stddef.h>

#include "tank_level_signals.h"

/* Parameter names are prefixed so macro substitution cannot hit a field designator. */
#define TANK_LOOP_LEVEL_ENTRY(arg_name, arg_id, arg_channel, arg_rate, arg_low, arg_high)          \
	{                                                                                          \
	    .signal_id = (arg_id),                                                                 \
	    .channel = (arg_channel),                                                              \
	    .update_rate_ms = (arg_rate),                                                          \
	    .valid_low_ma = (arg_low),                                                             \
	    .valid_high_ma = (arg_high),                                                           \
	},

static const struct tank_loop_level_config loops[] = {TANK_LEVEL_LOOPS(TANK_LOOP_LEVEL_ENTRY)};

#define LOOP_COUNT (sizeof(loops) / sizeof(loops[0]))

_Static_assert(LOOP_COUNT == TANK_LEVEL_LOOP_COUNT,
	       "the generated level table does not match its declared count");

size_t tank_loop_level_config_count(void)
{
	return LOOP_COUNT;
}

const struct tank_loop_level_config *tank_loop_level_config_at(size_t index)
{
	if (index >= LOOP_COUNT) {
		return NULL;
	}

	return &loops[index];
}

const struct tank_loop_level_config *tank_loop_level_config_by_id(uint16_t signal_id)
{
	for (size_t i = 0; i < LOOP_COUNT; i++) {
		if (loops[i].signal_id == signal_id) {
			return &loops[i];
		}
	}

	return NULL;
}

const struct tank_loop_level_config *tank_loop_level_config_by_channel(uint8_t channel)
{
	for (size_t i = 0; i < LOOP_COUNT; i++) {
		if (loops[i].channel == channel) {
			return &loops[i];
		}
	}

	return NULL;
}
