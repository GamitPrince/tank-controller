/*
 * The equipment-status contracts, taken from the signal list at build time.
 *
 * tank_equipment_status_signals.h is generated from interfaces/signals-v1.yaml
 * by firmware/scripts/gen_equipment_status_signals.py and is never committed,
 * so no signal id, channel number, contact sense or debounce figure is written
 * into C. If a contact is added to the signal list for this story, the table
 * below grows without any change here.
 *
 * The table is const: a caller can read a channel's contract but cannot alter
 * what the contract says, and there is nothing here to drive a channel with.
 */

#include "equipment_status.h"

#include <stddef.h>

#include "tank_equipment_status_signals.h"

/*
 * The parameter names are prefixed because macro substitution replaces a
 * parameter wherever its token appears, a field designator included: a
 * parameter called `channel` would turn `.channel = (channel)` into
 * `.1 = (1)`, which does not compile.
 */
#define TANK_EQUIPMENT_STATUS_ENTRY(arg_name, arg_id, arg_channel, arg_sense, arg_debounce,        \
				    arg_scan)                                                      \
	{                                                                                          \
	    .signal_id = (arg_id),                                                                 \
	    .channel = (arg_channel),                                                              \
	    .sense = (arg_sense),                                                                  \
	    .debounce_ms = (arg_debounce),                                                         \
	    .scan_interval_ms = (arg_scan),                                                        \
	},

static const struct tank_level_switch_config equipment_inputs[] = {
    TANK_EQUIPMENT_STATUS_INPUTS(TANK_EQUIPMENT_STATUS_ENTRY)};

#define EQUIPMENT_INPUT_COUNT (sizeof(equipment_inputs) / sizeof(equipment_inputs[0]))

/* The generator states the count as well, so a truncated table cannot build. */
_Static_assert(EQUIPMENT_INPUT_COUNT == TANK_EQUIPMENT_STATUS_INPUT_COUNT,
	       "the generated equipment status table does not match its declared count");

size_t tank_equipment_status_config_count(void)
{
	return EQUIPMENT_INPUT_COUNT;
}

const struct tank_level_switch_config *tank_equipment_status_config_at(size_t index)
{
	if (index >= EQUIPMENT_INPUT_COUNT) {
		return NULL;
	}

	return &equipment_inputs[index];
}

const struct tank_level_switch_config *tank_equipment_status_config_by_id(uint16_t signal_id)
{
	for (size_t i = 0; i < EQUIPMENT_INPUT_COUNT; i++) {
		if (equipment_inputs[i].signal_id == signal_id) {
			return &equipment_inputs[i];
		}
	}

	return NULL;
}
