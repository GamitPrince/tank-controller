/*
 * Take a scan every second and log it (S-059, P1-12, P1-14).
 *
 * One thread builds a scan from the inputs (S-058) on a fixed grid of
 * period_ms and appends it to the flash log (S-039). The grid does not drift:
 * each wait runs to the next grid point, however long the scan took. A scan
 * that overruns its slot skips the grid points it missed instead of catching
 * up in a burst, and the skips are counted.
 *
 * Logging does not depend on the network (decided 26 Nov 2026): the uplink
 * service (S-049) forwards the log on its own thread, at a lower priority.
 *
 * After each scan it logs, the service compares it with the one logged before
 * (tank_scan_prompt_change(), S-065). When a contact or a quality changed it
 * calls on_change, so the uplink can send at once instead of waiting for its
 * 5 s batch (NFR-01).
 *
 * seq starts at 1 for each boot and advances once per scan built, so a scan
 * the flash log failed to store shows up as a gap in seq.
 *
 * Read only: the inputs are read, never written. There is one service
 * thread, so at most one service runs at a time.
 */

#ifndef TANK_RECORD_SCAN_SERVICE_H_
#define TANK_RECORD_SCAN_SERVICE_H_

#include <stdint.h>

#include <zephyr/kernel.h>

#include "boot_time.h"
#include "flash_log.h"
#include "scan_builder.h"

struct tank_scan_service_config {
	/* The scan period; 1000 ms in Phase 1 (one record per second). */
	uint32_t period_ms;
	/* Signal list version the ids come from (the record's `sl`). */
	uint32_t sl;
};

struct tank_scan_service_inputs {
	const struct tank_scan_sources *sources;
	const struct tank_boot_time *bt;
	/*
	 * Held while a scan is built. Whoever updates the sources or the boot
	 * time from another thread takes it too. NULL when they never change
	 * while the service runs.
	 */
	struct k_mutex *lock;
	struct tank_flash_log *log;
	/* Called after a scan with a prompt change is logged; may be NULL. */
	void (*on_change)(void *ctx);
	void *change_ctx;
};

struct tank_scan_service_stats {
	uint32_t scans;
	uint32_t build_errors;
	uint32_t append_errors;
	/* Grid points skipped because a scan ran past its slot. */
	uint32_t skipped;
	/* Logged scans with a prompt change (S-065). */
	uint32_t changes;
	int last_error;
};

/* Treat the fields as private; read the counters through stats. */
struct tank_scan_service {
	struct tank_scan_service_inputs in;
	struct tank_scan_service_config cfg;
	struct k_thread thread;
	k_tid_t tid;
	atomic_t stopping;
	/* Given by stop, so a waiting thread wakes at once. */
	struct k_sem wake;
	uint32_t seq;
	struct tank_scan scan;
	/* The last scan logged, to compare the next one with. */
	struct tank_scan last_logged;
	bool have_last;
	struct tank_scan_service_stats stats;
};

/*
 * The grid point to wait for after a scan that was due at deadline_ms and
 * finished at now_ms: the first one after now_ms. *skipped is set to how many
 * grid points were missed in between.
 */
int64_t tank_scan_service_next_deadline(int64_t deadline_ms, int64_t now_ms, uint32_t period_ms,
					uint32_t *skipped);

/*
 * Start the service: the first scan at once, then one every period_ms. The
 * inputs must stay valid while it runs. Returns 0, -EINVAL, or -EALREADY when
 * a service is already running.
 */
int tank_scan_service_start(struct tank_scan_service *svc,
			    const struct tank_scan_service_inputs *in,
			    const struct tank_scan_service_config *cfg);

/*
 * Stop the thread after its current scan and wait for it to end. Returns 0,
 * or -EINVAL when svc is not running.
 */
int tank_scan_service_stop(struct tank_scan_service *svc);

/* The service's counters, or NULL when svc is NULL. */
const struct tank_scan_service_stats *tank_scan_service_stats(const struct tank_scan_service *svc);

#endif /* TANK_RECORD_SCAN_SERVICE_H_ */
