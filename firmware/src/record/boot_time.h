/*
 * Boot-relative time and SNTP reconciliation (S-038, P1-15).
 *
 * ADR-0004 decision 11: time is SNTP where available, otherwise
 * boot-relative, with a boot id and a "time not yet known" flag. This module
 * is the pure bookkeeping behind that: it never touches the network itself
 * (that is firmware/src/communications/clock_sync.h, which calls back in
 * here once a sync attempt succeeds or fails) and never reads the clock
 * itself (every call is given the caller's own uptime in milliseconds, from
 * k_uptime_get() in real firmware), so it is fully testable on native_sim
 * without a network stack.
 *
 * Record fields, from interfaces/records.cddl:
 *   boot  <- tank_boot_time_stamp.boot_id   (random, one per boot, in memory
 *                                            only: ADR-0004.11 ties records
 *                                            within one boot together, not
 *                                            across a power cycle)
 *   up    <- tank_boot_time_stamp.up_ms
 *   tk    <- tank_boot_time_stamp.tk
 *   t     <- tank_boot_time_stamp.t_s       (present only when tk is true)
 *
 * The 1 s agreement limit (tech lead, 2026-11-23) is checked on every sync:
 * if the new estimate disagrees with the previous one by more than the
 * limit, tank_boot_time_warning_active() reports true until a later sync
 * agrees again. The device raises this itself (signal 9004,
 * health_clock_sync_warning), so it stays visible even with the cloud link
 * down.
 */

#ifndef TANK_RECORD_BOOT_TIME_H_
#define TANK_RECORD_BOOT_TIME_H_

#include <stdbool.h>
#include <stdint.h>

/* interfaces/records.cddl: boot-id = bstr .size 16. */
#define TANK_BOOT_ID_LEN 16U

struct tank_boot_time_config {
	/* Maximum disagreement between two successive syncs before the clock
	 * drift warning is raised. 1000 ms (tech lead, 2026-11-23).
	 */
	uint32_t agreement_limit_ms;
};

/* Treat the fields as private; read state through the functions below. */
struct tank_boot_time {
	struct tank_boot_time_config config;
	uint8_t boot_id[TANK_BOOT_ID_LEN];
	bool time_known;
	bool warning_active;
	/* epoch_ms(up_ms) = up_ms + epoch_offset_ms, once time_known. */
	int64_t epoch_offset_ms;
};

/* What a record's time fields should carry for a reading taken at up_ms. */
struct tank_boot_time_stamp {
	uint8_t boot_id[TANK_BOOT_ID_LEN];
	uint32_t up_ms;
	bool tk;
	/* Unix seconds UTC. Valid, and only meaningful, when tk is true. */
	uint64_t t_s;
};

/*
 * Start a boot session. boot_id is 16 bytes the caller generated (a hardware
 * or CSPRNG source in real firmware; a fixed or scripted value in tests), so
 * this module stays deterministic. Time is unknown until the first
 * successful sync.
 *
 * Returns 0, or -EINVAL if a pointer is NULL or agreement_limit_ms is zero.
 */
int tank_boot_time_init(struct tank_boot_time *bt, const uint8_t boot_id[TANK_BOOT_ID_LEN],
			const struct tank_boot_time_config *config);

/*
 * Record a successful SNTP sync: the server's Unix time was epoch_ms when
 * this device's uptime was up_ms. The first sync after init (or after a
 * sync failure that never set time_known) establishes the offset without
 * raising the warning, since there is no prior estimate to disagree with.
 * A later sync that disagrees with the current offset by more than
 * config.agreement_limit_ms raises the warning; one that agrees clears it.
 * Either way the offset is updated, so later timestamps use the latest,
 * corrected estimate.
 *
 * Returns 0, or -EINVAL if bt is NULL or was not initialised.
 */
int tank_boot_time_record_sync(struct tank_boot_time *bt, uint32_t up_ms, uint64_t epoch_ms);

/*
 * Record that a sync attempt failed (server unreachable, timed out). Leaves
 * time_known and the warning state untouched: a failed retry is not itself
 * drift, and must never turn a known time back into "not yet known" or
 * silently clear a warning.
 *
 * Returns 0, or -EINVAL if bt is NULL or was not initialised.
 */
int tank_boot_time_record_sync_failure(struct tank_boot_time *bt);

/*
 * Fill out a record's time fields for a reading taken at up_ms.
 * Returns 0, or -EINVAL if a pointer is NULL or bt was not initialised.
 */
int tank_boot_time_stamp(const struct tank_boot_time *bt, uint32_t up_ms,
			  struct tank_boot_time_stamp *out);

/* True while the last sync disagreed with the previous estimate by more than
 * the agreement limit. False before the first sync (nothing to disagree
 * with yet) and after a sync that agrees.
 */
bool tank_boot_time_warning_active(const struct tank_boot_time *bt);

/* True once a sync has ever succeeded. */
bool tank_boot_time_known(const struct tank_boot_time *bt);

#endif /* TANK_RECORD_BOOT_TIME_H_ */
