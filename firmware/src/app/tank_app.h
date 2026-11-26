/*
 * Boot the firmware application (S-060, P1-12, P1-14).
 *
 * After hardware initialisation the application sets up every Phase 1 input
 * from the signal-list tables, mounts the flash log and starts the scan
 * service (S-059), whether or not a network is up (decided 26 Nov 2026).
 * Nothing here waits for the ESP32 or the cloud: records stay in the flash
 * log until the uplink, wired in a later story, forwards them.
 *
 * Until the acquisition stories feed the inputs from the pins, no input is
 * ever sampled, so every reading goes out as unconfigured or fault: honest,
 * never a made-up value.
 *
 * Read only: no input is driven and nothing is written to the safety chain.
 */

#ifndef TANK_APP_TANK_APP_H_
#define TANK_APP_TANK_APP_H_

#include <stdint.h>

#include <zephyr/kernel.h>

#include "boot_time.h"
#include "flash_log.h"
#include "scan_builder.h"
#include "scan_service.h"

/* Room for the inputs, above the Phase 1 signal list's 2, 6 and 15. */
#define TANK_APP_MAX_LEVELS 4U
#define TANK_APP_MAX_TEMPERATURES 8U
#define TANK_APP_MAX_CONTACTS 16U

struct tank_app_config {
	/* TANK_BOOT_ID_LEN random bytes, fresh for every boot (S-038). */
	const uint8_t *boot_id;
	struct tank_flash_log_config log;
	uint32_t scan_period_ms;
	/* Largest disagreement between two clock syncs before the warning. */
	uint32_t clock_agreement_limit_ms;
};

/* Treat the fields as private. */
struct tank_app {
	struct tank_boot_time bt;
	struct tank_flash_log log;
	struct tank_loop_level levels[TANK_APP_MAX_LEVELS];
	struct tank_product_temperature temperatures[TANK_APP_MAX_TEMPERATURES];
	/* Level switches, then alarm contacts, then equipment status. */
	struct tank_level_switch contacts[TANK_APP_MAX_CONTACTS];
	struct tank_scan_sources sources;
	/* Shared with the threads that will update the inputs and the clock. */
	struct k_mutex inputs_lock;
	struct tank_scan_service scan;
};

/*
 * Set up the inputs and the boot time, mount the flash log and start the scan
 * service. app must be zeroed (a static object is) or stopped. Returns 0;
 * -EINVAL for a NULL argument; -EALREADY while app is running; -ENOSPC if the
 * signal list has more inputs than TANK_APP_MAX_*; or the error of the step
 * that failed.
 */
int tank_app_start(struct tank_app *app, const struct tank_app_config *cfg);

/* Stop the scan service. Returns 0, or -EINVAL when app is not running. */
int tank_app_stop(struct tank_app *app);

/* What the application reads each scan, or NULL when app is NULL. */
const struct tank_scan_sources *tank_app_sources(const struct tank_app *app);

#endif /* TANK_APP_TANK_APP_H_ */
