/* Status-only reading of the hardwired level switches. See level_switch.h. */

#include "level_switch.h"

#include <errno.h>

/* Wrap-safe elapsed time between two free-running millisecond counts. */
static uint32_t elapsed_ms(uint32_t now_ms, uint32_t since_ms)
{
	return (uint32_t)(now_ms - since_ms);
}

static bool sense_is_known(enum tank_contact_sense sense)
{
	return (sense == TANK_CONTACT_NORMALLY_OPEN) || (sense == TANK_CONTACT_NORMALLY_CLOSED);
}

/*
 * Translate the raw input into a switch state. A normally closed contact
 * carries current while the switch is healthy, so a de-energised input, which
 * is also what a broken wire looks like, means asserted.
 */
static enum tank_switch_state state_of(const struct tank_level_switch_config *config,
				       bool input_energised)
{
	const bool asserted =
	    (config->sense == TANK_CONTACT_NORMALLY_CLOSED) ? !input_energised : input_energised;

	return asserted ? TANK_SWITCH_ASSERTED : TANK_SWITCH_CLEAR;
}

uint32_t tank_level_switch_live_window_ms(const struct tank_level_switch_config *config)
{
	if (config == NULL) {
		return 0;
	}

	return config->debounce_ms +
	       TANK_LEVEL_SWITCH_MISSED_SCANS_ALLOWED * config->scan_interval_ms;
}

int tank_level_switch_init(struct tank_level_switch *sw,
			   const struct tank_level_switch_config *config)
{
	if ((sw == NULL) || (config == NULL)) {
		return -EINVAL;
	}

	if (!sense_is_known(config->sense) || (config->scan_interval_ms == 0U)) {
		return -EINVAL;
	}

	sw->config = *config;
	sw->confirmed = TANK_SWITCH_UNKNOWN;
	sw->candidate = TANK_SWITCH_UNKNOWN;
	sw->candidate_since_ms = 0U;
	sw->confirmed_at_ms = 0U;
	sw->have_sample = false;

	return 0;
}

int tank_level_switch_sample(struct tank_level_switch *sw, bool input_energised, uint32_t now_ms)
{
	if ((sw == NULL) || (sw->config.scan_interval_ms == 0U)) {
		return -EINVAL;
	}

	const enum tank_switch_state sampled = state_of(&sw->config, input_energised);

	if (!sw->have_sample || (sampled != sw->candidate)) {
		sw->candidate = sampled;
		sw->candidate_since_ms = now_ms;
		sw->have_sample = true;
	}

	if (sampled == sw->confirmed) {
		/* Still the confirmed state, and now confirmed by a fresh sample. */
		sw->confirmed_at_ms = now_ms;
		return 0;
	}

	if (elapsed_ms(now_ms, sw->candidate_since_ms) >= sw->config.debounce_ms) {
		sw->confirmed = sampled;
		sw->confirmed_at_ms = now_ms;
	}

	return 0;
}

int tank_level_switch_status(const struct tank_level_switch *sw, uint32_t now_ms,
			     struct tank_level_switch_status *out)
{
	if ((sw == NULL) || (out == NULL)) {
		return -EINVAL;
	}

	const bool confirmed = (sw->confirmed != TANK_SWITCH_UNKNOWN);
	const bool fresh = elapsed_ms(now_ms, sw->confirmed_at_ms) <=
			   tank_level_switch_live_window_ms(&sw->config);

	out->signal_id = sw->config.signal_id;
	out->state = sw->confirmed;
	out->live = confirmed && fresh;

	return 0;
}
