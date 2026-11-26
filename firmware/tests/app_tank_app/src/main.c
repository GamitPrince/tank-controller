/*
 * ztest suite for the application boot (S-060) on native_sim's flash
 * simulator: every Phase 1 input is set up from the signal-list tables in
 * scan order, scans start without any network, an unsampled input is never
 * given a value, and bad configuration is refused.
 */

#include <errno.h>

#include <zephyr/kernel.h>
#include <zephyr/ztest.h>

#include "scan_gen.h"
#include "tank_app.h"

#define RING_SECTORS 16U
#define PERIOD_MS 50U
#define RUN_MS 120U
#define AGREEMENT_MS 1000U
#define PHASE1_LEVELS 2U
#define PHASE1_TEMPERATURES 6U
#define PHASE1_CONTACTS 15U

static const uint16_t scan_order[] = {1001, 1002, 2001, 2002, 2003, 2004, 2005, 2006,
				      3001, 3002, 3011, 3012, 3013, 3014, 3015, 3016,
				      3021, 3022, 3023, 3024, 3025, 3026, 3027};

static uint8_t boot_id[TANK_BOOT_ID_LEN];
static struct tank_app app;
static struct tank_log_item item;

static struct tank_app_config config(void)
{
	return (struct tank_app_config){.boot_id = boot_id,
					.log = scan_gen_log_config(RING_SECTORS),
					.scan_period_ms = PERIOD_MS,
					.clock_agreement_limit_ms = AGREEMENT_MS};
}

static void before_each(void *fixture)
{
	ARG_UNUSED(fixture);
	scan_gen_erase();
	for (uint8_t i = 0U; i < TANK_BOOT_ID_LEN; i++) {
		boot_id[i] = (uint8_t)(0xA0U + i);
	}
}

static void after_each(void *fixture)
{
	ARG_UNUSED(fixture);
	(void)tank_app_stop(&app);
}

ZTEST_SUITE(app_tank_app, NULL, NULL, before_each, after_each, NULL);

ZTEST(app_tank_app, test_every_input_is_set_up_in_scan_order)
{
	const struct tank_app_config cfg = config();
	const struct tank_scan_sources *src;

	zassert_ok(tank_app_start(&app, &cfg));
	src = tank_app_sources(&app);
	zassert_equal(src->level_count, PHASE1_LEVELS);
	zassert_equal(src->temperature_count, PHASE1_TEMPERATURES);
	zassert_equal(src->contact_count, PHASE1_CONTACTS);
	zassert_equal(src->level_count + src->temperature_count + src->contact_count,
		      ARRAY_SIZE(scan_order));
}

ZTEST(app_tank_app, test_scans_start_with_no_network_and_carry_no_made_up_value)
{
	const struct tank_app_config cfg = config();
	uint32_t scans = 0U;

	zassert_ok(tank_app_start(&app, &cfg));
	k_msleep(RUN_MS);
	zassert_ok(tank_app_stop(&app));

	while (tank_flash_log_read_next(&app.log, &item) == 0) {
		zassert_equal(item.kind, TANK_LOG_ITEM_SCAN);
		zassert_mem_equal(item.scan.boot_id, boot_id, TANK_BOOT_ID_LEN);
		zassert_equal(item.scan.sl, 1U);
		zassert_false(item.scan.tk, "no clock sync yet");
		zassert_equal(item.scan.count, ARRAY_SIZE(scan_order));
		for (uint8_t i = 0U; i < item.scan.count; i++) {
			zassert_equal(item.scan.r[i].id, scan_order[i]);
			zassert_false(item.scan.r[i].has_val, "signal %u was never sampled",
				      item.scan.r[i].id);
		}
		scans++;
	}
	zassert_true(scans >= RUN_MS / PERIOD_MS, "only %u scans", scans);
}

ZTEST(app_tank_app, test_a_running_app_is_not_restarted)
{
	const struct tank_app_config cfg = config();

	zassert_ok(tank_app_start(&app, &cfg));
	zassert_equal(tank_app_start(&app, &cfg), -EALREADY);
	zassert_ok(tank_app_stop(&app));
	zassert_ok(tank_app_start(&app, &cfg), "a stopped app starts again");
}

ZTEST(app_tank_app, test_bad_configuration_is_refused)
{
	struct tank_app_config cfg = config();

	zassert_equal(tank_app_start(NULL, &cfg), -EINVAL);
	zassert_equal(tank_app_start(&app, NULL), -EINVAL);
	cfg.boot_id = NULL;
	zassert_equal(tank_app_start(&app, &cfg), -EINVAL);
	cfg = config();
	cfg.clock_agreement_limit_ms = 0U;
	zassert_equal(tank_app_start(&app, &cfg), -EINVAL, "boot time");
	cfg = config();
	cfg.log.size = 0U;
	zassert_equal(tank_app_start(&app, &cfg), -EINVAL, "flash log");
	cfg = config();
	cfg.scan_period_ms = 0U;
	zassert_equal(tank_app_start(&app, &cfg), -EINVAL, "scan service");
	zassert_equal(tank_app_stop(NULL), -EINVAL);
	zassert_is_null(tank_app_sources(NULL));
}
