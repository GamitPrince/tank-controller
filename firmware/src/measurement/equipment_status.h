/*
 * Status-only reading of the plant equipment contacts.
 *
 * Story S-033 (P1-27). Signal ids 3021 to 3027 on optocoupler channels 3 to 9
 * are the inlet valve, inlet pump, outlet pump, outlet valve, mixture motor,
 * base heater and main heater. The signal list in interfaces/ owns those
 * numbers and firmware/scripts/gen_equipment_status_signals.py turns them into
 * the generated table this module serves (see equipment_status_config.c).
 *
 * These are NOT safety-chain reads. They report whether equipment is running,
 * not a trip or an interlock, so they live here in the measurement layer and
 * not in firmware/src/safety/, and they need neither the `safety` label nor
 * the EE's approval (tech lead, 23 Nov 2026). Phase 1 still only ever reads
 * them: nothing here may start, stop or command a valve, pump, motor or
 * heater, which is Phase 2 and needs different hardware.
 *
 * All seven contacts are normally open, so a closed contact means running and
 * an open one simply means not running. That is the opposite of the safety
 * and alarm channels, which are normally closed so that a broken wire reads
 * as alarm; the two senses are deliberately not harmonised. The debounce is
 * 5 s because contactors chatter on motor and pump starts and latency does not
 * matter for a running state the way it does for an alarm.
 *
 * The debounce, liveness and contact-sense state machine is not reimplemented
 * here. tank_level_switch (safety/level_switch.h) already expresses it in
 * terms generic enough to cover any debounced optocoupler contact, which is
 * how story P1-09 reuses it for the alarm contacts. Using that engine does
 * not make these signals safety reads, and this module does not touch
 * anything under firmware/src/safety/. Its states map onto equipment state as:
 * TANK_SWITCH_ASSERTED means running, TANK_SWITCH_CLEAR means not running, and
 * TANK_SWITCH_UNKNOWN or `live == false` means no trustworthy state, which a
 * caller must not show as live.
 */

#ifndef TANK_MEASUREMENT_EQUIPMENT_STATUS_H_
#define TANK_MEASUREMENT_EQUIPMENT_STATUS_H_

#include <stddef.h>
#include <stdint.h>

#include "level_switch.h"

/* How many equipment contacts story P1-27 reads, as the signal list defines them. */
size_t tank_equipment_status_config_count(void);

/* The index-th equipment contact's contract, or NULL if index is out of range. */
const struct tank_level_switch_config *tank_equipment_status_config_at(size_t index);

/* The contract for signal_id, or NULL if this story does not read it. */
const struct tank_level_switch_config *tank_equipment_status_config_by_id(uint16_t signal_id);

#endif /* TANK_MEASUREMENT_EQUIPMENT_STATUS_H_ */
