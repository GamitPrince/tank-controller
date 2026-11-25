/*
 * ztest suite for the append-only flash log (S-039, P1-14), on native_sim's
 * flash simulator. The simulator refuses to program flash that is not
 * erased, so these tests also prove the log only ever appends.
 */

#include <zephyr/drivers/flash.h>
#include <zephyr/ztest.h>

#include <errno.h>

#include "flash_log.h"
#include "scan_gen.h"

#define SMALL_RING 4U
#define MEDIUM_RING 16U
#define FILL_SCANS 2000U
#define SHORT_RUN 200U
#define READ_FIRST 20U
#define BEFORE_POWER 50U
#define BEFORE_TEAR 10U
#define AFTER_TEAR 5U

static struct tank_flash_log log;
static struct tank_log_item item;

static void mount(size_t sectors)
{
	struct tank_flash_log_config cfg = scan_gen_log_config(sectors);

	zassert_ok(tank_flash_log_mount(&log, &cfg));
}

static void append_run(uint8_t boot, uint32_t first, uint32_t last, bool sync)
{
	struct tank_scan s;

	for (uint32_t seq = first; seq <= last; seq++) {
		scan_gen(&s, boot, seq, sync);
		zassert_ok(tank_flash_log_append(&log, &s), "append %u", seq);
	}
}

static void expect_run(uint8_t boot, uint32_t first, uint32_t last, bool sync)
{
	for (uint32_t seq = first; seq <= last; seq++) {
		zassert_ok(tank_flash_log_read_next(&log, &item), "read %u", seq);
		scan_gen_check(&item, boot, seq, sync);
	}
}

static void before_each(void *fixture)
{
	ARG_UNUSED(fixture);
	scan_gen_erase();
}

ZTEST(flash_log, test_empty_log_has_nothing_to_read)
{
	struct tank_flash_log_config cfg = scan_gen_log_config(1U);

	zassert_equal(tank_flash_log_mount(&log, &cfg), -EINVAL, "one sector is no ring");
	zassert_equal(tank_flash_log_mount(&log, NULL), -EINVAL);
	zassert_equal(tank_flash_log_read_next(&log, &item), -EINVAL, "not mounted");
	mount(SMALL_RING);
	zassert_equal(tank_flash_log_read_next(&log, &item), -ENODATA);
	zassert_equal(tank_flash_log_lost_scans(&log), 0U);
}

ZTEST(flash_log, test_scans_read_back_in_order_with_original_times)
{
	mount(MEDIUM_RING);
	/* Crosses GEN_SYNC_SEQ: records made before the first sync stay tk false. */
	append_run(0U, GEN_SYNC_SEQ - SHORT_RUN, GEN_SYNC_SEQ + SHORT_RUN, true);
	expect_run(0U, GEN_SYNC_SEQ - SHORT_RUN, GEN_SYNC_SEQ + SHORT_RUN, true);
	zassert_equal(tank_flash_log_read_next(&log, &item), -ENODATA);
}

ZTEST(flash_log, test_power_cycle_resumes_after_the_last_delivered_scan)
{
	mount(MEDIUM_RING);
	append_run(0U, 1U, BEFORE_POWER, false);
	expect_run(0U, 1U, READ_FIRST, false);
	zassert_ok(tank_flash_log_ack(&log, item.end_pos));

	/* Power cycle: a new boot id, seq and up start again. */
	mount(MEDIUM_RING);
	append_run(1U, 1U, READ_FIRST, false);
	expect_run(0U, READ_FIRST + 1U, BEFORE_POWER, false);
	expect_run(1U, 1U, READ_FIRST, false);
	zassert_equal(tank_flash_log_read_next(&log, &item), -ENODATA);
}

ZTEST(flash_log, test_torn_write_loses_nothing_written_before_it)
{
	/* Type, length and half a payload: what a power cut mid-write leaves. */
	static const uint8_t torn[] = {0x02, 0x40, 0x00, 0xB0, 0xB0, 0xB0};
	struct tank_flash_log_config cfg = scan_gen_log_config(MEDIUM_RING);

	mount(MEDIUM_RING);
	append_run(0U, 1U, BEFORE_TEAR, false);
	zassert_ok(flash_write(cfg.flash, cfg.offset + log.head_off, torn, sizeof(torn)));

	mount(MEDIUM_RING);
	expect_run(0U, 1U, BEFORE_TEAR, false);
	zassert_equal(tank_flash_log_read_next(&log, &item), -ENODATA);
	append_run(0U, BEFORE_TEAR + 1U, BEFORE_TEAR + AFTER_TEAR, false);
	expect_run(0U, BEFORE_TEAR + 1U, BEFORE_TEAR + AFTER_TEAR, false);
}

ZTEST(flash_log, test_full_log_drops_oldest_and_records_a_gap)
{
	uint32_t lost = 0U;
	uint32_t kept = 0U;
	uint32_t next_seq = 0U;
	uint32_t first_lost = UINT32_MAX;
	uint32_t last_lost = 0U;
	uint32_t first_kept = 0U;

	mount(SMALL_RING);
	append_run(0U, 1U, FILL_SCANS, false);
	zassert_true(tank_flash_log_lost_scans(&log) > 0U, "the small ring must overflow");

	while (tank_flash_log_read_next(&log, &item) == 0) {
		if (item.kind == TANK_LOG_ITEM_GAP) {
			zassert_true(item.gap.first.seq <= item.gap.last.seq);
			zassert_false(item.gap.first.tk, "boot 0 never synced");
			lost += item.gap.lost;
			first_lost = MIN(first_lost, item.gap.first.seq);
			last_lost = MAX(last_lost, item.gap.last.seq);
			continue;
		}
		first_kept = (first_kept == 0U) ? item.scan.seq : first_kept;
		zassert_true(next_seq == 0U || item.scan.seq == next_seq, "no hole inside the log");
		scan_gen_check(&item, 0U, item.scan.seq, false);
		next_seq = item.scan.seq + 1U;
		kept++;
	}
	zassert_equal(lost, tank_flash_log_lost_scans(&log));
	zassert_equal(next_seq, FILL_SCANS + 1U, "the newest scans are kept");
	zassert_equal(kept + lost, FILL_SCANS, "every scan is either kept or counted lost");
	/* The gap records place the hole exactly: from the oldest scan up to the
	 * one before the oldest kept scan, even after gaps were carried forward.
	 */
	zassert_equal(first_lost, 1U);
	zassert_equal(last_lost + 1U, first_kept);
}

ZTEST(flash_log, test_ack_and_rewind)
{
	uint64_t first_end;

	mount(MEDIUM_RING);
	append_run(0U, 1U, READ_FIRST, false);
	expect_run(0U, 1U, 2U, false);
	first_end = item.end_pos;
	zassert_equal(tank_flash_log_ack(&log, UINT64_MAX), -EINVAL, "beyond what was written");
	zassert_ok(tank_flash_log_ack(&log, first_end));
	zassert_ok(tank_flash_log_ack(&log, first_end - 1U), "an old ack is ignored");
	expect_run(0U, 3U, 5U, false);
	tank_flash_log_rewind(&log);
	expect_run(0U, 3U, READ_FIRST, false);
	zassert_equal(tank_flash_log_append(&log, NULL), -EINVAL);
	zassert_equal(tank_flash_log_read_next(&log, NULL), -EINVAL);
	tank_flash_log_rewind(NULL);
	zassert_equal(tank_flash_log_lost_scans(NULL), 0U);
	zassert_equal(tank_flash_log_ack(NULL, 0U), -EINVAL);
}

ZTEST_SUITE(flash_log, NULL, NULL, before_each, NULL, NULL);
