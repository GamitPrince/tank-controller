/*
 * The two 4-20 mA level reads (radar and pressure), each with a quality flag.
 *
 * Story S-034 (P1-04). ADR-0002: radar level on AD4111 channel 1, pressure
 * level on channel 2. The signal list in interfaces/ owns the ids, channels,
 * update rates and valid ranges, and firmware/scripts/gen_level_signals.py
 * turns them into the generated table this module serves.
 *
 * ADR-0004 decision 10: the controller is send-only and level percent, volume
 * and mass are computed in the cloud. So this module reports the loop current
 * in mA and nothing derived from it; no tank geometry lives on the controller.
 *
 * Each channel is read and reported independently. Comparing radar against
 * pressure level is Phase 2, so nothing here averages, cross-checks or
 * substitutes one channel for the other.
 *
 * Quality, in the words of interfaces/records.cddl (see reading_quality.h):
 *   - an ADC or bus error, or a current beyond the transmitter failure limits
 *     (open circuit reads near 0 mA, a short or runaway near the top of the
 *     converter) is `fault`, and no value is reported;
 *   - a current between the failure limits and the signal's valid range (below
 *     4 mA or above 20 mA) is `out-of-range`; the current is still reported
 *     and never clamped, so a consumer sees how far out it sits;
 *   - a reading no longer refreshed becomes `stale`, never shown as live;
 *   - a channel not read yet is `unconfigured`.
 * Only `good` may be shown as a live measurement.
 */

#ifndef TANK_MEASUREMENT_LOOP_LEVEL_H_
#define TANK_MEASUREMENT_LOOP_LEVEL_H_

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "ad4111.h"
#include "reading_quality.h"

/*
 * Below this current the loop is treated as failed rather than merely low: a
 * broken wire or dead transmitter reads about 0 mA. Above the high limit the
 * transmitter or wiring has failed high. The figures follow NAMUR NE43
 * (3.6 mA and 21 mA failure signalling).
 *
 * [Confirm] with the EE that the transmitters follow NE43; the limits are
 * firmware choices until the transmitter data sheets are supplied.
 */
#define TANK_LOOP_LEVEL_FAULT_LOW_MA 3.6f
#define TANK_LOOP_LEVEL_FAULT_HIGH_MA 21.0f

/*
 * Updates that may be missed before a reading is reported stale.
 * [Confirm] firmware choice, same figure and reasoning as P1-06.
 */
#define TANK_LOOP_LEVEL_MISSED_UPDATES_ALLOWED 3U

/* One channel's contract, taken from the signal list. */
struct tank_loop_level_config {
	uint16_t signal_id;
	/* AD4111 channel, 1 or 2. */
	uint8_t channel;
	uint32_t update_rate_ms;
	float valid_low_ma;
	float valid_high_ma;
};

/* One channel's reading state. Treat the fields as private. */
struct tank_loop_level {
	struct tank_loop_level_config config;
	enum tank_reading_quality quality;
	float current_ma;
	uint32_t sampled_at_ms;
	bool have_reading;
};

/* What a caller may report for a channel. */
struct tank_loop_level_status {
	uint16_t signal_id;
	enum tank_reading_quality quality;
	/* Loop current in mA. Not to be reported when quality is fault or unconfigured. */
	float current_ma;
	/* True only when quality is good. */
	bool live;
	/* Milliseconds since the reading this status reports was taken. */
	uint32_t age_ms;
};

/*
 * Prepare a channel from its contract.
 *
 * Returns 0 on success, or -EINVAL if a pointer is NULL, the channel is
 * outside the AD4111 channels used, update_rate_ms is zero, or the valid
 * range is empty or inverted. On failure level is left untouched.
 */
int tank_loop_level_init(struct tank_loop_level *level,
			 const struct tank_loop_level_config *config);

/*
 * Take one decoded AD4111 conversion for this channel, sampled at now_ms.
 * now_ms is a free-running millisecond count; wrap-around is harmless.
 *
 * Returns 0 on success, or -EINVAL if a pointer is NULL, level was not
 * initialised, or reading belongs to a different channel (so a conversion can
 * never be reported under another channel's signal id). On failure level is
 * left untouched.
 */
int tank_loop_level_update(struct tank_loop_level *level, const struct tank_ad4111_reading *reading,
			   uint32_t now_ms);

/* Report the channel as of now_ms. Returns 0, or -EINVAL if a pointer is NULL. */
int tank_loop_level_status(const struct tank_loop_level *level, uint32_t now_ms,
			   struct tank_loop_level_status *out);

/* How long a reading stays live without a fresh one. */
uint32_t tank_loop_level_live_window_ms(const struct tank_loop_level_config *config);

/* How many channels story P1-04 reads, as the signal list defines them. */
size_t tank_loop_level_config_count(void);

/* The index-th contract, or NULL if index is out of range. */
const struct tank_loop_level_config *tank_loop_level_config_at(size_t index);

/* The contract for signal_id, or NULL if this story does not read it. */
const struct tank_loop_level_config *tank_loop_level_config_by_id(uint16_t signal_id);

/* The contract for an AD4111 channel, or NULL if this story does not use it. */
const struct tank_loop_level_config *tank_loop_level_config_by_channel(uint8_t channel);

#endif /* TANK_MEASUREMENT_LOOP_LEVEL_H_ */
