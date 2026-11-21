/*
 * Status-only reading of the hardwired level switches.
 *
 * Story S-022 (P1-05). Channel 1 is the high-high level trip and channel 2 the
 * low-low heater cut-off; the signal list in interfaces/ owns those numbers and
 * firmware/scripts/gen_safety_signals.py turns them into the generated table
 * this module serves (see level_switch_config.c).
 *
 * SAFETY (AGENTS.md section 1, ADR-0002, ADR-0003): these channels are part of
 * the plant's hardwired safety chain, which Phase 1 only ever *reads*. The
 * switches trip the plant by themselves, through wiring this controller is not
 * part of. Everything here is therefore input-only by construction: the API
 * takes samples and hands back a state, and offers no way to drive, latch,
 * inhibit or acknowledge a channel. Nothing in this module may gain an output,
 * relay, coil or acknowledgement path; that would be a phase change and a
 * safety change, not a feature.
 *
 * Both channels are normally closed, so a de-energised switch or a broken wire
 * reads as asserted (alarm) and never as healthy. The debouncer deliberately
 * does not smooth that away: a channel stuck in the asserted state is reported
 * as asserted.
 *
 * A state is only reported as live while fresh samples keep confirming it. A
 * channel that stops being sampled, or that chatters so fast that no state ever
 * survives the debounce window, reports its last confirmed state with
 * `live == false` instead of presenting it as current, because stale data must
 * never be shown as live (AGENTS.md section 7).
 */

#ifndef TANK_SAFETY_LEVEL_SWITCH_H_
#define TANK_SAFETY_LEVEL_SWITCH_H_

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* How the field contact is wired, as the signal list states per channel. */
enum tank_contact_sense {
	/* Energised input means the switch is asserted. */
	TANK_CONTACT_NORMALLY_OPEN = 0,
	/* De-energised input, including a broken wire, means asserted. */
	TANK_CONTACT_NORMALLY_CLOSED = 1,
};

enum tank_switch_state {
	/* No state has survived the debounce window yet. */
	TANK_SWITCH_UNKNOWN = 0,
	/* The switch is not asserted: level below high-high, or above low-low. */
	TANK_SWITCH_CLEAR = 1,
	/* The switch is asserted, or its circuit is broken. */
	TANK_SWITCH_ASSERTED = 2,
};

/*
 * How long a confirmed state stays live without a fresh confirming sample,
 * expressed as the debounce window plus the scan intervals that may be missed
 * inside it. At the signal list's 200 ms debounce and 50 ms scan that is
 * 400 ms, far inside the five-second NFR-01 budget.
 *
 * [Confirm] the number of missed scans tolerated is a firmware choice, not an
 * EE figure: four is one full debounce window's worth of samples.
 */
#define TANK_LEVEL_SWITCH_MISSED_SCANS_ALLOWED 4U

/* One channel's contract, taken from the signal list. Read-only by nature. */
struct tank_level_switch_config {
	/* Signal id the record carries for this switch. */
	uint16_t signal_id;
	/* Optocoupler input channel the switch is wired to. */
	uint8_t channel;
	enum tank_contact_sense sense;
	uint32_t debounce_ms;
	uint32_t scan_interval_ms;
};

/* Debounce state for one channel. Treat the fields as private. */
struct tank_level_switch {
	struct tank_level_switch_config config;
	enum tank_switch_state confirmed;
	enum tank_switch_state candidate;
	uint32_t candidate_since_ms;
	uint32_t confirmed_at_ms;
	bool have_sample;
};

/* What a caller may report for a channel. */
struct tank_level_switch_status {
	uint16_t signal_id;
	enum tank_switch_state state;
	/* False when the state is stale or never confirmed: do not show as live. */
	bool live;
};

/*
 * Prepare sw to read the channel described by config.
 *
 * Returns 0 on success, or -EINVAL if either pointer is NULL, the contact sense
 * is not a known enumerator, or scan_interval_ms is zero. On failure sw is left
 * untouched.
 */
int tank_level_switch_init(struct tank_level_switch *sw,
			   const struct tank_level_switch_config *config);

/*
 * Feed one sample of the optocoupler input, taken at now_ms.
 *
 * input_energised is the raw electrical state of the input, not an alarm: the
 * channel's contact sense decides what it means. A state becomes the confirmed
 * state once it has held for the channel's debounce window; a sample agreeing
 * with the confirmed state refreshes its liveness.
 *
 * now_ms is a free-running millisecond count; differences are computed so that
 * wrap-around is harmless.
 *
 * Returns 0 on success, or -EINVAL if sw is NULL or was not initialised.
 */
int tank_level_switch_sample(struct tank_level_switch *sw, bool input_energised, uint32_t now_ms);

/*
 * Report the channel's state as of now_ms into out.
 *
 * Returns 0 on success, or -EINVAL if either pointer is NULL.
 */
int tank_level_switch_status(const struct tank_level_switch *sw, uint32_t now_ms,
			     struct tank_level_switch_status *out);

/* How long a confirmed state of this channel stays live without a new sample. */
uint32_t tank_level_switch_live_window_ms(const struct tank_level_switch_config *config);

/* How many switches story P1-05 reads, as the signal list defines them. */
size_t tank_level_switch_config_count(void);

/* The index-th switch contract, or NULL if index is out of range. */
const struct tank_level_switch_config *tank_level_switch_config_at(size_t index);

/* The contract for signal_id, or NULL if this story does not read it. */
const struct tank_level_switch_config *tank_level_switch_config_by_id(uint16_t signal_id);

#endif /* TANK_SAFETY_LEVEL_SWITCH_H_ */
