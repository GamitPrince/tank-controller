/*
 * Status-only reading of the hardwired alarm and trip contacts.
 *
 * Story S-031 (P1-09). Signal ids 3011 to 3016 on optocoupler channels 10 to
 * 15 are the low/high pressure level alarm, low/high radar level alarm, low
 * mixture temperature alarm and dry-run alarm; the signal list in
 * interfaces/ owns those numbers and firmware/scripts/gen_safety_signals.py
 * turns them into the generated table this module serves (see
 * alarm_input_config.c).
 *
 * SAFETY (AGENTS.md section 1, ADR-0002, ADR-0003): these contacts come from
 * field devices that carry their own safety mechanisms. Phase 1 only ever
 * *reads* them. There is no reset, no acknowledge-to-device, no bypass and no
 * output here, and nothing in this module may gain one; that would be a
 * phase change and a safety change, not a feature.
 *
 * All six contacts are normally closed, so a de-energised device or a broken
 * wire reads as alarm, never as healthy.
 *
 * The debounce, liveness and contact-sense state machine is not reimplemented
 * here: story P1-05's tank_level_switch type and functions (level_switch.h)
 * already express it in terms generic enough to cover any debounced
 * optocoupler contact, level switch or alarm alike, so this module only adds
 * the P1-09 contract table that engine runs against.
 */

#ifndef TANK_SAFETY_ALARM_INPUT_H_
#define TANK_SAFETY_ALARM_INPUT_H_

#include <stddef.h>
#include <stdint.h>

#include "level_switch.h"

/* How many alarm contacts story P1-09 reads, as the signal list defines them. */
size_t tank_alarm_input_config_count(void);

/* The index-th alarm contact's contract, or NULL if index is out of range. */
const struct tank_level_switch_config *tank_alarm_input_config_at(size_t index);

/* The contract for signal_id, or NULL if this story does not read it. */
const struct tank_level_switch_config *tank_alarm_input_config_by_id(uint16_t signal_id);

#endif /* TANK_SAFETY_ALARM_INPUT_H_ */
