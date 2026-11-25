/*
 * ztest suite for forwarding the flash log after an outage (S-039, P1-14).
 *
 * A fake cloud stands in for the MQTT sender (P1-12): while the link is down
 * it refuses every batch; once up it checks each scan against the generator,
 * so original timestamps, boot ids and the "time not yet known" flag are
 * verified end to end, and that scans arrive in order with no hole that a
 * gap item does not account for.
 */

#include <zephyr/ztest.h>

#include <errno.h>

#include "flash_log.h"
#include "log_forwarder.h"
#include "scan_gen.h"

#define FULL_SIZE_SECTORS 2048U /* the 8 MB W25Q64 */
#define SMALL_RING 4U
#define DAY_SCANS 86400U
#define POWER_CUT_AT (DAY_SCANS / 2U)
#define POLL_EVERY 60U
#define BATCH_CAP 32U
#define FILL_SCANS 2000U
#define LONG_RUN_SCANS 20000U
#define ONLINE_POLL_EVERY 10U
/* Usable log after a reserve, from the capacity calculation in the spec. */
#define USABLE_BYTES (7680U * 1024U)
#define TYPICAL_DAY_BYTES (3U * 1024U * 1024U)

struct fake_cloud {
	bool link_up;
	uint32_t delivered;
	uint32_t lost;
	uint8_t last_boot;
	uint32_t last_seq;
	bool gap_pending;
};

static struct tank_flash_log log;
static struct tank_log_item batch[BATCH_CAP];
static struct fake_cloud cloud;

/* Boot 0 never reaches an SNTP server; boot 1 syncs at GEN_SYNC_SEQ. */
static bool synced(uint8_t boot)
{
	return boot == 1U;
}

static void check_order(struct fake_cloud *c, uint8_t boot, uint32_t seq)
{
	bool next_in_boot = boot == c->last_boot && seq == c->last_seq + 1U;
	bool new_boot = boot > c->last_boot && seq == 1U;

	zassert_true(c->delivered == 0U || next_in_boot || new_boot || c->gap_pending,
		     "hole before boot %u seq %u", boot, seq);
	c->last_boot = boot;
	c->last_seq = seq;
	c->gap_pending = false;
}

static int fake_send(void *ctx, const struct tank_log_item *items, size_t count)
{
	struct fake_cloud *c = ctx;

	if (!c->link_up) {
		return -ENOTCONN;
	}
	for (size_t i = 0U; i < count; i++) {
		uint8_t boot = (uint8_t)(items[i].scan.boot_id[0] - 0xB0U);

		if (items[i].kind == TANK_LOG_ITEM_GAP) {
			c->lost += items[i].lost_scans;
			c->gap_pending = true;
			continue;
		}
		scan_gen_check(&items[i], boot, items[i].scan.seq, synced(boot));
		check_order(c, boot, items[i].scan.seq);
		c->delivered++;
	}
	return 0;
}

static const struct tank_log_forwarder fw = {
    .log = &log, .send_fn = fake_send, .ctx = &cloud, .batch = batch, .batch_cap = BATCH_CAP};

static void mount(size_t sectors)
{
	struct tank_flash_log_config cfg = scan_gen_log_config(sectors);

	zassert_ok(tank_flash_log_mount(&log, &cfg));
}

static void append(uint8_t boot, uint32_t seq)
{
	struct tank_scan s;

	scan_gen(&s, boot, seq, synced(boot));
	zassert_ok(tank_flash_log_append(&log, &s), "append boot %u seq %u", boot, seq);
}

static void drain(void)
{
	int rc;

	cloud.link_up = true;
	while ((rc = tank_log_forwarder_poll(&fw)) > 0) {
	}
	zassert_equal(rc, 0);
}

static void before_each(void *fixture)
{
	ARG_UNUSED(fixture);
	scan_gen_erase();
	cloud = (struct fake_cloud){0};
}

ZTEST(log_forwarder, test_24_hour_outage_loses_nothing)
{
	uint64_t used;

	mount(FULL_SIZE_SECTORS);
	for (uint32_t i = 0U; i < DAY_SCANS; i++) {
		if (i == POWER_CUT_AT) {
			mount(FULL_SIZE_SECTORS);
		}
		append(i < POWER_CUT_AT ? 0U : 1U,
		       i < POWER_CUT_AT ? i + 1U : i - POWER_CUT_AT + 1U);
		if (i % POLL_EVERY == 0U) {
			zassert_equal(tank_log_forwarder_poll(&fw), -ENOTCONN);
		}
	}
	used = (uint64_t)log.head_seq * log.cfg.sector_size + log.head_off;
	TC_PRINT("24 h of %u signals used %llu bytes of flash\n", GEN_SIGNALS,
		 (unsigned long long)used);
	zassert_true(used < TYPICAL_DAY_BYTES && used < USABLE_BYTES);

	drain();
	zassert_equal(cloud.delivered, DAY_SCANS);
	zassert_equal(cloud.lost, 0U);
	zassert_equal(tank_flash_log_lost_scans(&log), 0U);
}

ZTEST(log_forwarder, test_full_log_during_outage_forwards_a_gap)
{
	mount(SMALL_RING);
	for (uint32_t seq = 1U; seq <= FILL_SCANS; seq++) {
		append(0U, seq);
	}
	drain();
	zassert_true(cloud.lost > 0U);
	zassert_equal(cloud.lost, tank_flash_log_lost_scans(&log));
	zassert_equal(cloud.delivered + cloud.lost, FILL_SCANS);
	zassert_equal(cloud.last_seq, FILL_SCANS, "the newest scans are kept");
}

ZTEST(log_forwarder, test_long_run_online_wraps_the_ring_without_loss)
{
	mount(SMALL_RING);
	cloud.link_up = true;
	for (uint32_t seq = 1U; seq <= LONG_RUN_SCANS; seq++) {
		append(0U, seq);
		if (seq % ONLINE_POLL_EVERY == 0U) {
			zassert_true(tank_log_forwarder_poll(&fw) > 0);
		}
	}
	drain();
	zassert_equal(cloud.delivered, LONG_RUN_SCANS);
	zassert_equal(cloud.lost, 0U);
	/* Sectors are reused round robin, so wear spreads over the whole ring. */
	zassert_true(log.head_seq > SMALL_RING * SMALL_RING, "the ring wrapped many times");
}

ZTEST(log_forwarder, test_caught_up_and_bad_arguments)
{
	struct tank_log_forwarder no_batch = fw;

	mount(SMALL_RING);
	cloud.link_up = true;
	zassert_equal(tank_log_forwarder_poll(&fw), 0, "nothing to send");
	no_batch.batch_cap = 0U;
	zassert_equal(tank_log_forwarder_poll(&no_batch), -EINVAL);
	zassert_equal(tank_log_forwarder_poll(NULL), -EINVAL);
}

ZTEST_SUITE(log_forwarder, NULL, NULL, before_each, NULL, NULL);
