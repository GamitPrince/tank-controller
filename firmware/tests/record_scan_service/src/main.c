/*
 * ztest suite for the scan service (S-059) on native_sim's flash simulator:
 * the grid policy, one scan per period stored in seq order without drift, a
 * held input lock delaying a scan and skipping the grid points it missed, a
 * prompt stop, and build and append errors being counted, not hidden.
 */

#include <errno.h>

#include <zephyr/kernel.h>
#include <zephyr/ztest.h>

#include "scan_gen.h"
#include "scan_service.h"

#define RING_SECTORS 16U
#define SL 1U
#define PERIOD_MS 50U
#define LONG_MS 10000U
#define RUN_MS 520U
/* Wake-up jitter on a busy host; drift would grow with n instead. */
#define GRID_SLACK_MS 15
#define LOCK_HOLD_MS 230U
#define SETTLE_MS 10U
#define STOP_SLACK_MS 20U
#define STEADY_MS 160U
#define LOOP_MA 12.0f
#define LOOP_UA 12000

static const struct tank_boot_time_config bt_cfg = {.agreement_limit_ms = 1000U};
static const struct tank_loop_level_config loop_cfg = {.signal_id = 1001U,
						       .channel = 1U,
						       .update_rate_ms = 1000U,
						       .valid_low_ma = 4.0f,
						       .valid_high_ma = 20.0f};

static uint8_t boot_id[TANK_BOOT_ID_LEN];
static struct tank_flash_log log;
static struct tank_boot_time bt;
static struct tank_loop_level level;
static struct tank_scan_sources src = {.levels = &level, .level_count = 1U};
static struct tank_scan_service svc;
static struct tank_log_item item;
static K_MUTEX_DEFINE(inputs_lock);

static void start(uint32_t period_ms, const struct tank_scan_sources *sources,
		  struct tank_flash_log *to)
{
	const struct tank_scan_service_inputs in = {
	    .sources = sources, .bt = &bt, .lock = &inputs_lock, .log = to};
	const struct tank_scan_service_config cfg = {.period_ms = period_ms, .sl = SL};

	zassert_ok(tank_scan_service_start(&svc, &in, &cfg));
}

static void before_each(void *fixture)
{
	struct tank_flash_log_config cfg = scan_gen_log_config(RING_SECTORS);
	struct tank_ad4111_reading r = {.current_ma = LOOP_MA, .channel = 1U};

	ARG_UNUSED(fixture);
	scan_gen_erase();
	zassert_ok(tank_flash_log_mount(&log, &cfg));
	zassert_ok(tank_boot_time_init(&bt, boot_id, &bt_cfg));
	zassert_ok(tank_loop_level_init(&level, &loop_cfg));
	zassert_ok(tank_loop_level_update(&level, &r, k_uptime_get_32()));
}

static void after_each(void *fixture)
{
	ARG_UNUSED(fixture);
	(void)tank_scan_service_stop(&svc);
}

ZTEST_SUITE(scan_service, NULL, NULL, before_each, after_each, NULL);

ZTEST(scan_service, test_next_deadline_stays_on_the_grid)
{
	uint32_t skipped;

	zassert_equal(tank_scan_service_next_deadline(1000, 1010, 1000U, &skipped), 2000);
	zassert_equal(skipped, 0U);
	zassert_equal(tank_scan_service_next_deadline(1000, 3500, 1000U, &skipped), 4000);
	zassert_equal(skipped, 2U, "2000 and 3000 were missed");
	zassert_equal(tank_scan_service_next_deadline(1000, 2000, 1000U, &skipped), 3000);
	zassert_equal(skipped, 1U);
}

ZTEST(scan_service, test_one_scan_per_period_in_seq_order_without_drift)
{
	const struct tank_scan_service_stats *st;
	uint32_t first_up = 0U;
	uint32_t n = 0U;

	start(PERIOD_MS, &src, &log);
	k_msleep(RUN_MS);
	zassert_ok(tank_scan_service_stop(&svc));
	st = tank_scan_service_stats(&svc);
	zassert_true(st->scans >= RUN_MS / PERIOD_MS && st->scans <= RUN_MS / PERIOD_MS + 2U,
		     "%u scans in %u ms", st->scans, RUN_MS);
	zassert_equal(st->skipped + st->build_errors + st->append_errors, 0U);

	while (tank_flash_log_read_next(&log, &item) == 0) {
		zassert_equal(item.kind, TANK_LOG_ITEM_SCAN);
		zassert_equal(item.scan.seq, n + 1U);
		if (n == 0U) {
			first_up = item.scan.up_ms;
		}
		zassert_within((int64_t)(item.scan.up_ms - first_up), (int64_t)n * PERIOD_MS,
			       GRID_SLACK_MS, "scan %u drifted", n);
		zassert_equal(item.scan.r[0].val, LOOP_UA);
		zassert_equal(item.scan.r[0].q, TANK_QUALITY_GOOD);
		n++;
	}
	zassert_equal(n, st->scans, "every scan was logged");
}

ZTEST(scan_service, test_held_lock_delays_the_scan_and_skips_missed_points)
{
	const struct tank_scan_service_stats *st = tank_scan_service_stats(&svc);
	uint32_t during;

	zassert_ok(k_mutex_lock(&inputs_lock, K_FOREVER));
	start(PERIOD_MS, &src, &log);
	k_msleep(LOCK_HOLD_MS);
	during = st->scans;
	zassert_ok(k_mutex_unlock(&inputs_lock));
	k_msleep(PERIOD_MS + SETTLE_MS);

	zassert_equal(during, 0U, "no scan while the inputs were locked");
	zassert_true(st->scans >= 1U);
	zassert_true(st->skipped >= LOCK_HOLD_MS / PERIOD_MS - 1U, "skipped %u", st->skipped);
}

ZTEST(scan_service, test_stop_is_prompt_and_arguments_are_checked)
{
	const struct tank_scan_service_inputs in = {.sources = &src, .bt = &bt, .log = &log};
	const struct tank_scan_service_inputs no_log = {.sources = &src, .bt = &bt};
	const struct tank_scan_service_config cfg = {.period_ms = PERIOD_MS, .sl = SL};
	const struct tank_scan_service_config no_period = {.sl = SL};
	struct tank_scan_service other = {0};
	int64_t stop_at;

	zassert_equal(tank_scan_service_start(NULL, &in, &cfg), -EINVAL);
	zassert_equal(tank_scan_service_start(&svc, NULL, &cfg), -EINVAL);
	zassert_equal(tank_scan_service_start(&svc, &in, NULL), -EINVAL);
	zassert_equal(tank_scan_service_start(&svc, &no_log, &cfg), -EINVAL);
	zassert_equal(tank_scan_service_start(&svc, &in, &no_period), -EINVAL);
	zassert_equal(tank_scan_service_stop(NULL), -EINVAL);
	zassert_equal(tank_scan_service_stop(&other), -EINVAL, "never started");
	zassert_is_null(tank_scan_service_stats(NULL));

	start(LONG_MS, &src, &log);
	zassert_equal(tank_scan_service_start(&other, &in, &cfg), -EALREADY);
	k_msleep(SETTLE_MS);
	zassert_equal(tank_scan_service_stats(&svc)->scans, 1U, "the first scan is at once");
	stop_at = k_uptime_get();
	zassert_ok(tank_scan_service_stop(&svc));
	zassert_true(k_uptime_get() - stop_at < STOP_SLACK_MS, "stop waited out the period");
	zassert_equal(tank_scan_service_stop(&svc), -EINVAL, "already stopped");
}

ZTEST(scan_service, test_build_and_append_errors_are_counted)
{
	static const struct tank_scan_sources empty = {0};
	static struct tank_flash_log unmounted;
	const struct tank_scan_service_stats *st = tank_scan_service_stats(&svc);

	start(PERIOD_MS, &empty, &log);
	k_msleep(PERIOD_MS + SETTLE_MS);
	zassert_ok(tank_scan_service_stop(&svc));
	zassert_true(st->build_errors >= 1U);
	zassert_equal(st->last_error, -EINVAL);
	zassert_equal(st->scans, 0U);
	zassert_equal(tank_flash_log_read_next(&log, &item), -ENODATA, "nothing was logged");

	start(PERIOD_MS, &src, &unmounted);
	k_msleep(PERIOD_MS + SETTLE_MS);
	zassert_ok(tank_scan_service_stop(&svc));
	zassert_true(st->append_errors >= 1U);
	zassert_equal(st->scans, 0U);
}

static atomic_t changes_seen;

static void count_change(void *ctx)
{
	ARG_UNUSED(ctx);
	atomic_inc(&changes_seen);
}

ZTEST(scan_service, test_a_quality_change_calls_on_change_once)
{
	const struct tank_scan_service_inputs in = {.sources = &src,
						    .bt = &bt,
						    .lock = &inputs_lock,
						    .log = &log,
						    .on_change = count_change};
	const struct tank_scan_service_config cfg = {.period_ms = PERIOD_MS, .sl = SL};
	struct tank_ad4111_reading fault = {
	    .current_ma = LOOP_MA, .channel = 1U, .adc_error = true};

	atomic_set(&changes_seen, 0);
	zassert_ok(tank_scan_service_start(&svc, &in, &cfg));
	k_msleep(STEADY_MS);
	zassert_equal(atomic_get(&changes_seen), 0, "steady scans wait for their batch");

	zassert_ok(k_mutex_lock(&inputs_lock, K_FOREVER));
	zassert_ok(tank_loop_level_update(&level, &fault, k_uptime_get_32()));
	zassert_ok(k_mutex_unlock(&inputs_lock));
	k_msleep(2U * PERIOD_MS + SETTLE_MS);
	zassert_equal(atomic_get(&changes_seen), 1, "one change, one call");
	zassert_equal(tank_scan_service_stats(&svc)->changes, 1U);
}
