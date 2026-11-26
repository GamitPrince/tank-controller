/*
 * ztest suite for the uplink service thread (S-049) on native_sim's flash
 * simulator: the delay policy, draining a backlog without idle waits, the
 * idle and retry cadence on the kernel clock, a prompt stop, and a scan
 * thread appending while the service forwards.
 *
 * A scripted cloud stands in for the uplink (S-045): it can refuse the
 * first batches, can be slow, and fails the test on any scan that arrives
 * out of order or twice.
 */

#include <errno.h>
#include <string.h>

#include <zephyr/kernel.h>
#include <zephyr/ztest.h>

#include "flash_log.h"
#include "log_forwarder.h"
#include "scan_gen.h"
#include "uplink_service.h"

#define RING_SECTORS 16U
#define BATCH_CAP 4U
#define BOOT 0U
#define LONG_MS 10000U
#define SHORT_MS 50U
#define RETRY_MS 100U
#define BACKLOG_SCANS 20U
#define FAILED_SENDS 2U
#define IDLE_RUN_MS 300U
#define STEP_MS 5U
#define DRAIN_LIMIT_MS 2000U
#define STOP_SLACK_MS 20U
#define ARRIVAL_SLACK_MS 25U
#define CONCURRENT_SCANS 300U
#define SLOW_SEND_MS 2U
#define APPENDER_STACK 4096
#define APPENDER_PRIORITY K_PRIO_PREEMPT(5)

static struct {
	uint32_t fail_left;
	uint32_t slow_ms;
	uint32_t next_seq;
	uint32_t received;
	int64_t first_ok_ms;
} cloud;

static struct tank_flash_log log;
static struct tank_log_item batch[BATCH_CAP];
static struct tank_uplink_service svc;

static int cloud_send(void *ctx, const struct tank_log_item *items, size_t count)
{
	ARG_UNUSED(ctx);
	if (cloud.slow_ms > 0U) {
		k_msleep(cloud.slow_ms);
	}
	if (cloud.fail_left > 0U) {
		cloud.fail_left--;
		return -ETIMEDOUT;
	}
	if (cloud.received == 0U) {
		cloud.first_ok_ms = k_uptime_get();
	}
	for (size_t i = 0U; i < count; i++) {
		zassert_equal(items[i].kind, TANK_LOG_ITEM_SCAN);
		zassert_equal(items[i].scan.seq, cloud.next_seq, "got %u, want %u",
			      items[i].scan.seq, cloud.next_seq);
		cloud.next_seq++;
		cloud.received++;
	}
	return (int)count;
}

static const struct tank_log_forwarder fw = {
    .log = &log, .send_fn = cloud_send, .batch = batch, .batch_cap = BATCH_CAP};

static void append_scans(uint32_t from, uint32_t to)
{
	struct tank_scan s;

	for (uint32_t seq = from; seq <= to; seq++) {
		scan_gen(&s, BOOT, seq, false);
		zassert_ok(tank_flash_log_append(&log, &s));
	}
}

static void start(uint32_t idle_ms, uint32_t retry_ms)
{
	const struct tank_uplink_service_config cfg = {.idle_ms = idle_ms, .retry_ms = retry_ms};

	zassert_ok(tank_uplink_service_start(&svc, &fw, &cfg));
}

/* Wait until the cloud holds want scans; returns the time it took. */
static int64_t wait_for(uint32_t want)
{
	int64_t start_ms = k_uptime_get();

	while (cloud.received < want) {
		zassert_true(k_uptime_get() - start_ms < DRAIN_LIMIT_MS, "only %u of %u arrived",
			     cloud.received, want);
		k_msleep(STEP_MS);
	}
	return k_uptime_get() - start_ms;
}

static void before_each(void *fixture)
{
	struct tank_flash_log_config cfg = scan_gen_log_config(RING_SECTORS);

	ARG_UNUSED(fixture);
	memset(&cloud, 0, sizeof(cloud));
	cloud.next_seq = 1U;
	scan_gen_erase();
	zassert_ok(tank_flash_log_mount(&log, &cfg));
}

static void after_each(void *fixture)
{
	ARG_UNUSED(fixture);
	(void)tank_uplink_service_stop(&svc);
}

ZTEST_SUITE(uplink_service, NULL, NULL, before_each, after_each, NULL);

ZTEST(uplink_service, test_next_delay_policy)
{
	const struct tank_uplink_service_config cfg = {.idle_ms = SHORT_MS, .retry_ms = RETRY_MS};

	zassert_equal(tank_uplink_service_next_delay(BATCH_CAP, &cfg), 0U);
	zassert_equal(tank_uplink_service_next_delay(0, &cfg), SHORT_MS);
	zassert_equal(tank_uplink_service_next_delay(-ETIMEDOUT, &cfg), RETRY_MS);
}

ZTEST(uplink_service, test_a_part_batch_means_caught_up)
{
	const struct tank_uplink_service_config cfg = {
	    .idle_ms = SHORT_MS, .retry_ms = RETRY_MS, .full_batch = BATCH_CAP};

	zassert_equal(tank_uplink_service_next_delay(BATCH_CAP, &cfg), 0U, "more may be waiting");
	zassert_equal(tank_uplink_service_next_delay(BATCH_CAP - 1, &cfg), SHORT_MS);
	zassert_equal(tank_uplink_service_next_delay(0, &cfg), SHORT_MS);
	zassert_equal(tank_uplink_service_next_delay(-EIO, &cfg), RETRY_MS);
}

ZTEST(uplink_service, test_backlog_drains_without_idle_waits_and_stop_is_prompt)
{
	int64_t stop_at;

	append_scans(1U, BACKLOG_SCANS);
	start(LONG_MS, LONG_MS);
	zassert_true(wait_for(BACKLOG_SCANS) < LONG_MS, "waited idle between batches");
	zassert_equal(tank_uplink_service_stats(&svc)->delivered, BACKLOG_SCANS);
	zassert_equal(tank_uplink_service_stats(&svc)->errors, 0U);

	stop_at = k_uptime_get();
	zassert_ok(tank_uplink_service_stop(&svc));
	zassert_true(k_uptime_get() - stop_at < STOP_SLACK_MS, "stop waited out the idle sleep");
}

ZTEST(uplink_service, test_caught_up_polls_every_idle_period)
{
	uint32_t polls;

	start(SHORT_MS, LONG_MS);
	k_msleep(IDLE_RUN_MS);
	polls = tank_uplink_service_stats(&svc)->polls;
	zassert_true(polls >= IDLE_RUN_MS / SHORT_MS && polls <= IDLE_RUN_MS / SHORT_MS + 1U,
		     "%u polls in %u ms", polls, IDLE_RUN_MS);
	append_scans(1U, BATCH_CAP);
	zassert_true(wait_for(BATCH_CAP) <= SHORT_MS + ARRIVAL_SLACK_MS,
		     "a new scan waited too long");
}

ZTEST(uplink_service, test_failed_link_waits_retry_period_then_recovers)
{
	int64_t start_ms;

	cloud.fail_left = FAILED_SENDS;
	append_scans(1U, BATCH_CAP);
	start_ms = k_uptime_get();
	start(LONG_MS, RETRY_MS);
	wait_for(BATCH_CAP);
	zassert_true(cloud.first_ok_ms - start_ms >= FAILED_SENDS * RETRY_MS,
		     "retried after %lld ms", cloud.first_ok_ms - start_ms);
	zassert_true(cloud.first_ok_ms - start_ms < (FAILED_SENDS + 1U) * RETRY_MS);
	zassert_equal(tank_uplink_service_stats(&svc)->errors, FAILED_SENDS);
	zassert_equal(tank_uplink_service_stats(&svc)->last_error, -ETIMEDOUT);
	zassert_equal(tank_uplink_service_stats(&svc)->delivered, BATCH_CAP);
}

ZTEST(uplink_service, test_start_stop_arguments)
{
	const struct tank_uplink_service_config cfg = {.idle_ms = SHORT_MS, .retry_ms = RETRY_MS};
	struct tank_uplink_service other = {0};

	zassert_equal(tank_uplink_service_start(NULL, &fw, &cfg), -EINVAL);
	zassert_equal(tank_uplink_service_start(&svc, NULL, &cfg), -EINVAL);
	zassert_equal(tank_uplink_service_start(&svc, &fw, NULL), -EINVAL);
	zassert_equal(tank_uplink_service_stop(NULL), -EINVAL);
	zassert_equal(tank_uplink_service_stop(&other), -EINVAL, "never started");
	start(SHORT_MS, RETRY_MS);
	zassert_equal(tank_uplink_service_start(&other, &fw, &cfg), -EALREADY);
	zassert_ok(tank_uplink_service_stop(&svc));
	zassert_equal(tank_uplink_service_stop(&svc), -EINVAL, "already stopped");
	zassert_is_null(tank_uplink_service_stats(NULL));
}

K_THREAD_STACK_DEFINE(appender_stack, APPENDER_STACK);
static struct k_thread appender;

static void appender_main(void *p1, void *p2, void *p3)
{
	struct tank_scan s;

	ARG_UNUSED(p1);
	ARG_UNUSED(p2);
	ARG_UNUSED(p3);
	for (uint32_t seq = 1U; seq <= CONCURRENT_SCANS; seq++) {
		scan_gen(&s, BOOT, seq, false);
		zassert_ok(tank_flash_log_append(&log, &s));
		k_msleep(1);
	}
}

ZTEST(uplink_service, test_scan_thread_appends_while_service_forwards)
{
	cloud.slow_ms = SLOW_SEND_MS;
	start(SLOW_SEND_MS, SLOW_SEND_MS);
	k_thread_create(&appender, appender_stack, K_THREAD_STACK_SIZEOF(appender_stack),
			appender_main, NULL, NULL, NULL, APPENDER_PRIORITY, 0, K_NO_WAIT);
	zassert_ok(k_thread_join(&appender, K_FOREVER));
	zassert_true(cloud.received > 0U, "the service forwarded while the appender ran");
	wait_for(CONCURRENT_SCANS);
	zassert_ok(tank_uplink_service_stop(&svc));
	zassert_equal(cloud.received, CONCURRENT_SCANS, "each scan exactly once");
	zassert_equal(tank_flash_log_lost_scans(&log), 0U);
}

ZTEST(uplink_service, test_a_kick_cuts_the_idle_wait_short)
{
	struct tank_uplink_service never_started = {0};

	start(LONG_MS, LONG_MS);
	k_msleep(STEP_MS);
	zassert_equal(tank_uplink_service_stats(&svc)->polls, 1U,
		      "now waiting out the idle period");
	append_scans(1U, BATCH_CAP);
	zassert_ok(tank_uplink_service_kick(&svc));
	zassert_true(wait_for(BATCH_CAP) <= ARRIVAL_SLACK_MS, "the kick did not wake the poll");
	zassert_equal(tank_uplink_service_kick(NULL), -EINVAL);
	zassert_equal(tank_uplink_service_kick(&never_started), -EINVAL);
}
