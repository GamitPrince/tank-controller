/*
 * The level-switch contracts, taken from the signal list at build time.
 *
 * tank_safety_signals.h is generated from interfaces/signals-v1.yaml by
 * firmware/scripts/gen_safety_signals.py and is never committed, so no signal
 * id, channel number, contact sense or debounce figure is written into C. If a
 * switch is added to the signal list for this story, the table below grows
 * without any change here.
 *
 * The table is const: a caller can read a channel's contract but cannot alter
 * what the contract says, and there is nothing here to drive a channel with.
 */

#include "level_switch.h"

#include <stddef.h>

#include "tank_safety_signals.h"

#define TANK_LEVEL_SWITCH_ENTRY(name, id, channel, sense, debounce, scan)                          \
	{                                                                                          \
	    .signal_id = (id),                                                                     \
	    .channel = (channel),                                                                  \
	    .sense = (sense),                                                                      \
	    .debounce_ms = (debounce),                                                             \
	    .scan_interval_ms = (scan),                                                            \
	},

static const struct tank_level_switch_config switches[] = {
    TANK_SAFETY_LEVEL_SWITCHES(TANK_LEVEL_SWITCH_ENTRY)};

#define SWITCH_COUNT (sizeof(switches) / sizeof(switches[0]))

/* The generator states the count as well, so a truncated table cannot build. */
_Static_assert(SWITCH_COUNT == TANK_SAFETY_LEVEL_SWITCH_COUNT,
	       "the generated switch table does not match its declared count");

size_t tank_level_switch_config_count(void)
{
	return SWITCH_COUNT;
}

const struct tank_level_switch_config *tank_level_switch_config_at(size_t index)
{
	if (index >= SWITCH_COUNT) {
		return NULL;
	}

	return &switches[index];
}

const struct tank_level_switch_config *tank_level_switch_config_by_id(uint16_t signal_id)
{
	for (size_t i = 0; i < SWITCH_COUNT; i++) {
		if (switches[i].signal_id == signal_id) {
			return &switches[i];
		}
	}

	return NULL;
}
