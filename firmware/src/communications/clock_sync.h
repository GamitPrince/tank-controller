/*
 * SNTP retry policy and health reporting for boot-relative time (S-038, P1-15).
 *
 * This is the "when to try" and "what to report" layer on top of
 * firmware/src/record/boot_time.h's pure bookkeeping. The actual network
 * call is injected as sync_fn, so this module is fully testable on
 * native_sim with a fake sync function; the real transport
 * (firmware/src/communications/sntp_client.h, against a public NTP pool per
 * the tech lead, 2026-11-23) is wired in only once there is a real network
 * stack to call it from, which this story does not build.
 *
 * Reports signals 9001 (health_uptime) and 9004 (health_clock_sync_warning)
 * from interfaces/signals-v1.yaml, generated into tank_health_signals.h by
 * firmware/scripts/gen_health_signals.py.
 */

#ifndef TANK_COMMUNICATIONS_CLOCK_SYNC_H_
#define TANK_COMMUNICATIONS_CLOCK_SYNC_H_

#include <stdbool.h>
#include <stdint.h>

#include "boot_time.h"
#include "reading_quality.h"

struct tank_clock_sync_config {
	/* How often to attempt a sync: on the first poll, and again once
	 * this many milliseconds have passed since the last attempt,
	 * whether that attempt succeeded or failed.
	 */
	uint32_t retry_interval_ms;
};

/*
 * epoch_ms_out receives the server's Unix time in milliseconds on success.
 * Returns 0 on success, or a negative error code (the value is not
 * inspected, only whether it is 0) on failure. ctx is whatever
 * tank_clock_sync_init was given, opaque to this module.
 */
typedef int (*tank_sntp_sync_fn)(void *ctx, uint64_t *epoch_ms_out);

/* Treat the fields as private; read state through the functions below. */
struct tank_clock_sync {
	struct tank_clock_sync_config config;
	struct tank_boot_time *boot_time;
	tank_sntp_sync_fn sync_fn;
	void *sync_ctx;
	bool have_attempted;
	uint32_t last_attempt_up_ms;
};

/*
 * boot_time must already be initialised (tank_boot_time_init) and outlive
 * this struct. Returns 0, or -EINVAL if a required pointer is NULL or
 * retry_interval_ms is zero.
 */
int tank_clock_sync_init(struct tank_clock_sync *cs, const struct tank_clock_sync_config *config,
			 struct tank_boot_time *boot_time, tank_sntp_sync_fn sync_fn, void *sync_ctx);

/*
 * Call periodically (e.g. from the main loop) with the current uptime.
 * Attempts a sync if none has been tried yet, or if retry_interval_ms has
 * passed since the last attempt, and feeds the result into boot_time. A
 * failed sync is not itself a firmware error, so this still returns 0.
 *
 * Returns 0, or -EINVAL if cs is NULL or was not initialised.
 */
int tank_clock_sync_poll(struct tank_clock_sync *cs, uint32_t up_ms);

/* Signal 9001, health_uptime: seconds since boot. Always quality good. */
struct tank_health_uptime_status {
	uint16_t signal_id;
	enum tank_reading_quality quality;
	uint32_t uptime_s;
};

/* Signal 9004, health_clock_sync_warning. Always quality good: the device
 * always knows whether it is currently warning, even if it does not yet
 * know the time.
 */
struct tank_health_clock_sync_warning_status {
	uint16_t signal_id;
	enum tank_reading_quality quality;
	bool warning;
};

/* Returns 0, or -EINVAL if a pointer is NULL or cs was not initialised. */
int tank_clock_sync_uptime_status(const struct tank_clock_sync *cs, uint32_t up_ms,
				   struct tank_health_uptime_status *out);

/* Returns 0, or -EINVAL if a pointer is NULL or cs was not initialised. */
int tank_clock_sync_warning_status(const struct tank_clock_sync *cs,
				    struct tank_health_clock_sync_warning_status *out);

#endif /* TANK_COMMUNICATIONS_CLOCK_SYNC_H_ */
