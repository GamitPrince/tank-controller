/*
 * ztest suite for forwarding the flash log over the UART link (S-045).
 *
 * The real flash log (S-039) on native_sim's simulated flash, log_forwarder,
 * the uplink and the S-043 sender talk over sim_link to a real
 * link_receiver standing in for the ESP32. Each record the ESP32 passes up
 * is compared, by length and CRC-16, with the CBOR the expected scan
 * encodes to (S-044), so order and "confirmed once" are checked end to end.
 */

#include <errno.h>
#include <zephyr/ztest.h>

#include "flash_log.h"
#include "link_sender.h"
#include "log_forwarder.h"
#include "record_cbor.h"
#include "scan_gen.h"
#include "sim_link.h"
#include "uplink.h"

#define DEV_ID "tank-test-01"
#define RING_SECTORS 4U
#define BATCH_CAP 8U
#define TIMEOUT_MS 3000U
#define ATTEMPTS 3U
#define NOISE_MS 700U
#define BATCH_SCANS 5U
#define GOOD_BEFORE_FAULT 2U
#define FILL_SCANS 2000U
#define BOOT 0U

static struct tank_flash_log log;
static struct tank_log_item batch[BATCH_CAP];
static struct tank_uplink up;
static uint32_t gaps_confirmed;

/* The uplink, counting the gap items it reports confirmed. */
static int send_and_count(void *ctx, const struct tank_log_item *items, size_t count)
{
	int rc = tank_uplink_send(ctx, items, count);

	for (int i = 0; i < rc; i++) {
		gaps_confirmed += (items[i].kind == TANK_LOG_ITEM_GAP) ? 1U : 0U;
	}
	return rc;
}

static const struct tank_log_forwarder fw = {
    .log = &log, .send_fn = send_and_count, .ctx = &up, .batch = batch, .batch_cap = BATCH_CAP};

static const struct tank_uplink_io io = {
    .write_fn = sim_link_write, .read_fn = sim_link_read, .now_fn = sim_link_now};

static const struct tank_link_sender_config link_cfg = {.ack_timeout_ms = TIMEOUT_MS,
							.max_attempts = ATTEMPTS};

static void append_scans(uint32_t count)
{
	struct tank_scan s;

	for (uint32_t seq = 1U; seq <= count; seq++) {
		scan_gen(&s, BOOT, seq, false);
		zassert_ok(tank_flash_log_append(&log, &s));
	}
}

/* Assert that the ESP32's record at index is scan seq, encoded. */
static void check_record(uint32_t index, uint32_t seq)
{
	static uint8_t buf[TANK_RECORD_CBOR_MAX];
	struct tank_log_item item = {.kind = TANK_LOG_ITEM_SCAN};
	size_t len;

	scan_gen(&item.scan, BOOT, seq, false);
	len = tank_record_cbor_encode_item(DEV_ID, &item, buf, sizeof(buf));
	zassert_true(len > 0U);
	zassert_equal(sim.log_len[index], len, "record %u length", index);
	zassert_equal(sim.log_crc[index], tank_link_crc16(buf, len), "record %u is not seq %u",
		      index, seq);
}

/* The ESP32 passed up scans 1 to count, each once, in order. */
static void check_records(uint32_t count)
{
	zassert_equal(sim.delivered, count, "the ESP32 passed up %u records", sim.delivered);
	for (uint32_t i = 0U; i < count; i++) {
		check_record(i, i + 1U);
	}
}

static void before_each(void *fixture)
{
	struct tank_flash_log_config cfg = scan_gen_log_config(RING_SECTORS);

	ARG_UNUSED(fixture);
	scan_gen_erase();
	zassert_ok(tank_flash_log_mount(&log, &cfg));
	sim_link_reset();
	gaps_confirmed = 0U;
	zassert_ok(tank_uplink_init(&up, DEV_ID, &link_cfg, &io));
}

ZTEST_SUITE(uplink, NULL, NULL, before_each, NULL, NULL);

ZTEST(uplink, test_clean_batch_is_confirmed_in_order)
{
	append_scans(BATCH_SCANS);
	zassert_equal(tank_log_forwarder_poll(&fw), BATCH_SCANS);
	zassert_equal(tank_log_forwarder_poll(&fw), 0, "the whole batch was acked");
	check_records(BATCH_SCANS);
	zassert_equal(tank_uplink_stats(&up)->sent, BATCH_SCANS);
	zassert_equal(tank_uplink_stats(&up)->confirmed, BATCH_SCANS);
	zassert_equal(sim.clock_ms, 0U, "no waiting on a clean link");
}

ZTEST(uplink, test_scans_and_a_gap_are_forwarded)
{
	int rc;

	append_scans(FILL_SCANS);
	zassert_true(tank_flash_log_lost_scans(&log) > 0U, "the small ring overflowed");
	while ((rc = tank_log_forwarder_poll(&fw)) > 0) {
	}
	zassert_equal(rc, 0);
	zassert_true(gaps_confirmed > 0U);
	zassert_equal(sim.delivered, FILL_SCANS - tank_flash_log_lost_scans(&log) + gaps_confirmed,
		      "every kept scan and every gap reached the ESP32 once");
	zassert_equal(tank_uplink_stats(&up)->confirmed, sim.delivered);
	zassert_equal(tank_link_receiver_stats(&sim.rx)->duplicates, 0U);
}

ZTEST(uplink, test_lost_record_is_resent_and_confirmed_once)
{
	append_scans(1U);
	sim.drop_records = 1U;
	zassert_equal(tank_log_forwarder_poll(&fw), 1);
	check_records(1U);
	zassert_equal(tank_link_sender_stats(&up.sender)->retransmitted, 1U);
	zassert_equal(sim.clock_ms, TIMEOUT_MS, "resent after one timeout");
}

ZTEST(uplink, test_lost_delivered_is_recovered_and_confirmed_once)
{
	append_scans(1U);
	sim.drop_delivered = 1U;
	zassert_equal(tank_log_forwarder_poll(&fw), 1);
	check_records(1U);
	zassert_equal(tank_link_receiver_stats(&sim.rx)->duplicates, 1U, "the resend reconfirmed");
	zassert_equal(tank_uplink_stats(&up)->confirmed, 1U);
}

ZTEST(uplink, test_give_up_mid_batch_keeps_the_confirmed_items)
{
	append_scans(BATCH_SCANS);
	sim.dead_after = GOOD_BEFORE_FAULT;
	zassert_equal(tank_log_forwarder_poll(&fw), GOOD_BEFORE_FAULT, "a partial batch");
	zassert_equal(tank_uplink_stats(&up)->link_give_ups, 1U);
	zassert_equal(tank_log_forwarder_poll(&fw), -ETIMEDOUT, "still down");

	sim.dead_after = 0U;
	zassert_equal(tank_log_forwarder_poll(&fw), BATCH_SCANS - GOOD_BEFORE_FAULT,
		      "only the unconfirmed items are sent again");
	zassert_equal(tank_log_forwarder_poll(&fw), 0);
	check_records(BATCH_SCANS);
}

ZTEST(uplink, test_encode_failure_is_counted_and_not_delivered)
{
	/* A gap that counts no lost scans is refused by the encoder. */
	struct tank_log_item items[2] = {{.kind = TANK_LOG_ITEM_SCAN}, {.kind = TANK_LOG_ITEM_GAP}};

	scan_gen(&items[0].scan, BOOT, 1U, false);
	zassert_equal(tank_uplink_send(&up, items, 2U), 1, "only the first is confirmed");
	zassert_equal(tank_uplink_send(&up, &items[1], 1U), -EINVAL);
	zassert_equal(tank_uplink_stats(&up)->encode_failures, 2U);
	check_records(1U);
}

ZTEST(uplink, test_read_error_is_returned_and_nothing_is_acked)
{
	append_scans(1U);
	sim.read_error = -EIO;
	zassert_equal(tank_log_forwarder_poll(&fw), -EIO);
	zassert_false(tank_link_sender_busy(&up.sender), "the RECORD was abandoned");
	/*
	 * The RECORD reached the ESP32 before the read failed, so the resend,
	 * with a new seq, reaches it again; the cloud deduplicates on boot id
	 * and seq (ADR-0004 decision 11).
	 */
	zassert_equal(tank_log_forwarder_poll(&fw), 1);
	zassert_equal(sim.delivered, 2U);
	check_record(0U, 1U);
	check_record(1U, 1U);
}

ZTEST(uplink, test_time_on_one_item_is_bounded)
{
	append_scans(1U);
	sim.dead = true;
	sim.noise_every_ms = NOISE_MS;
	zassert_equal(tank_log_forwarder_poll(&fw), -ETIMEDOUT);
	zassert_true(sim.clock_ms <= ATTEMPTS * TIMEOUT_MS + TIMEOUT_MS, "took %u ms",
		     sim.clock_ms);
	zassert_equal(sim.clock_ms, ATTEMPTS * TIMEOUT_MS, "noise never delays a resend");
	zassert_equal(tank_link_sender_stats(&up.sender)->sent +
			  tank_link_sender_stats(&up.sender)->retransmitted,
		      ATTEMPTS);
}

ZTEST(uplink, test_bad_arguments)
{
	struct tank_uplink_io no_read = io;
	struct tank_uplink_io no_clock = io;

	no_read.read_fn = NULL;
	no_clock.now_fn = NULL;
	zassert_equal(tank_uplink_init(NULL, DEV_ID, &link_cfg, &io), -EINVAL);
	zassert_equal(tank_uplink_init(&up, NULL, &link_cfg, &io), -EINVAL);
	zassert_equal(tank_uplink_init(&up, DEV_ID, &link_cfg, NULL), -EINVAL);
	zassert_equal(tank_uplink_init(&up, DEV_ID, &link_cfg, &no_read), -EINVAL);
	zassert_equal(tank_uplink_init(&up, DEV_ID, &link_cfg, &no_clock), -EINVAL);
	zassert_equal(tank_uplink_init(&up, DEV_ID, NULL, &io), -EINVAL);
	zassert_equal(tank_uplink_send(NULL, batch, 1U), -EINVAL);
	zassert_equal(tank_uplink_send(&up, NULL, 1U), -EINVAL);
	zassert_equal(tank_uplink_send(&up, batch, 0U), -EINVAL);
	zassert_is_null(tank_uplink_stats(NULL));
}
