/*
 * Tank-AI FRDM-MCXN947 firmware entry point (S-060).
 *
 * Starts acquisition and logging after hardware initialisation, with or
 * without a network (decided 26 Nov 2026); see tank_app.h. The flash log's
 * partition is the devicetree's chosen tank,log-partition.
 */

#include <zephyr/kernel.h>
#include <zephyr/random/random.h>
#include <zephyr/storage/flash_map.h>

#include "tank_app.h"

#define LOG_PARTITION DT_CHOSEN(tank_log_partition)

/* One consolidated record per second (decided 26 Nov 2026). */
#define SCAN_PERIOD_MS 1000U
/* Two clock syncs further apart than this raise the warning (P1-15). */
#define CLOCK_AGREEMENT_LIMIT_MS 1000U
/* Erase sector of the W25Q64 and of native_sim's simulated flash. */
#define LOG_SECTOR_SIZE 4096U
/* S-039: a full scan every 60, the delivered position persisted every 60 acks. */
#define LOG_FULL_INTERVAL 60U
#define LOG_ACK_PERSIST_INTERVAL 60U

static struct tank_app app;

int main(void)
{
	uint8_t boot_id[TANK_BOOT_ID_LEN];
	const struct tank_app_config cfg = {
	    .boot_id = boot_id,
	    .log =
		{
		    .flash = PARTITION_NODE_DEVICE(LOG_PARTITION),
		    .offset = PARTITION_NODE_OFFSET(LOG_PARTITION),
		    .size = PARTITION_NODE_SIZE(LOG_PARTITION),
		    .sector_size = LOG_SECTOR_SIZE,
		    .full_interval = LOG_FULL_INTERVAL,
		    .ack_persist_interval = LOG_ACK_PERSIST_INTERVAL,
		},
	    .scan_period_ms = SCAN_PERIOD_MS,
	    .clock_agreement_limit_ms = CLOCK_AGREEMENT_LIMIT_MS,
	};

	sys_rand_get(boot_id, sizeof(boot_id));
	return tank_app_start(&app, &cfg);
}
