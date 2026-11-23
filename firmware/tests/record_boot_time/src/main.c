/*
 * ztest suite for boot-relative time bookkeeping (S-038, P1-15).
 *
 * This is pure logic: every call is given its own uptime, boot id and sync
 * results, so the whole suite runs deterministically on native_sim with no
 * network and no real clock.
 */

#include <zephyr/ztest.h>

#include <errno.h>
#include <stdint.h>

#include "boot_time.h"

#define AGREEMENT_LIMIT_MS 1000U

static const uint8_t BOOT_ID_A[TANK_BOOT_ID_LEN] = {1, 2,  3,  4,  5,  6,  7,  8,
						    9, 10, 11, 12, 13, 14, 15, 16};
static const uint8_t BOOT_ID_B[TANK_BOOT_ID_LEN] = {16, 15, 14, 13, 12, 11, 10, 9,
						    8,	7,  6,	5,  4,	3,  2,	1};

static struct tank_boot_time bt_for(const uint8_t boot_id[TANK_BOOT_ID_LEN])
{
	struct tank_boot_time bt;
	const struct tank_boot_time_config config = {.agreement_limit_ms = AGREEMENT_LIMIT_MS};

	zassert_equal(tank_boot_time_init(&bt, boot_id, &config), 0);
	return bt;
}

static struct tank_boot_time_stamp stamp_of(const struct tank_boot_time *bt, uint32_t up_ms)
{
	struct tank_boot_time_stamp stamp = {0};

	zassert_equal(tank_boot_time_stamp(bt, up_ms, &stamp), 0);
	return stamp;
}

ZTEST_SUITE(record_boot_time, NULL, NULL, NULL, NULL, NULL);

ZTEST(record_boot_time, test_init_rejects_bad_arguments)
{
	struct tank_boot_time bt;
	const struct tank_boot_time_config good_config = {.agreement_limit_ms = AGREEMENT_LIMIT_MS};
	const struct tank_boot_time_config zero_config = {.agreement_limit_ms = 0U};

	zassert_equal(tank_boot_time_init(NULL, BOOT_ID_A, &good_config), -EINVAL);
	zassert_equal(tank_boot_time_init(&bt, NULL, &good_config), -EINVAL);
	zassert_equal(tank_boot_time_init(&bt, BOOT_ID_A, NULL), -EINVAL);
	zassert_equal(tank_boot_time_init(&bt, BOOT_ID_A, &zero_config), -EINVAL);
}

ZTEST(record_boot_time, test_time_not_known_before_any_sync)
{
	struct tank_boot_time bt = bt_for(BOOT_ID_A);
	const struct tank_boot_time_stamp stamp = stamp_of(&bt, 5000U);

	zassert_false(tank_boot_time_known(&bt));
	zassert_false(stamp.tk);
	/* Never a placeholder absolute time while time is unknown. */
	zassert_equal(stamp.t_s, 0U);
	zassert_equal(stamp.up_ms, 5000U);
	zassert_mem_equal(stamp.boot_id, BOOT_ID_A, TANK_BOOT_ID_LEN);
	zassert_false(tank_boot_time_warning_active(&bt));
}

ZTEST(record_boot_time, test_normal_sync_sets_time_known_without_a_warning)
{
	struct tank_boot_time bt = bt_for(BOOT_ID_A);
	/* Server time 1,700,000,000.000 s when uptime was 1000 ms. */
	const uint64_t epoch_ms = 1700000000000ULL;

	zassert_equal(tank_boot_time_record_sync(&bt, 1000U, epoch_ms), 0);
	zassert_true(tank_boot_time_known(&bt));
	zassert_false(tank_boot_time_warning_active(&bt));

	/* 4000 ms later, the stamped time has moved on by the same amount. */
	const struct tank_boot_time_stamp stamp = stamp_of(&bt, 5000U);

	zassert_true(stamp.tk);
	zassert_equal(stamp.t_s, (epoch_ms / 1000U) + 4U);
}

ZTEST(record_boot_time, test_sync_failure_leaves_time_unknown)
{
	struct tank_boot_time bt = bt_for(BOOT_ID_A);

	zassert_equal(tank_boot_time_record_sync_failure(&bt), 0);
	zassert_equal(tank_boot_time_record_sync_failure(&bt), 0);
	zassert_false(tank_boot_time_known(&bt));

	const struct tank_boot_time_stamp stamp = stamp_of(&bt, 9000U);

	zassert_false(stamp.tk);
	zassert_equal(stamp.t_s, 0U);
}

ZTEST(record_boot_time, test_sync_reachable_only_after_buffering)
{
	struct tank_boot_time bt = bt_for(BOOT_ID_A);
	const uint64_t epoch_ms = 1700000000000ULL;

	/* Hours of failed attempts before the network comes up. */
	for (int i = 0; i < 10; i++) {
		zassert_equal(tank_boot_time_record_sync_failure(&bt), 0);
	}
	zassert_false(tank_boot_time_known(&bt));

	/* The first success, however late, must not be treated as drift. */
	zassert_equal(tank_boot_time_record_sync(&bt, 3600000U, epoch_ms), 0);
	zassert_true(tank_boot_time_known(&bt));
	zassert_false(tank_boot_time_warning_active(&bt));
}

ZTEST(record_boot_time, test_drift_beyond_limit_raises_warning)
{
	struct tank_boot_time bt = bt_for(BOOT_ID_A);
	const uint64_t first_epoch_ms = 1700000000000ULL;

	zassert_equal(tank_boot_time_record_sync(&bt, 0U, first_epoch_ms), 0);
	zassert_false(tank_boot_time_warning_active(&bt));

	/* A later sync (clock stepped backwards) disagrees by 5 s, well
	 * beyond the 1 s limit.
	 */
	const uint64_t stepped_epoch_ms = first_epoch_ms - 5000U;

	zassert_equal(tank_boot_time_record_sync(&bt, 10000U, stepped_epoch_ms), 0);
	zassert_true(tank_boot_time_warning_active(&bt));

	/* The corrected offset is still in effect for later timestamps: no
	 * record is ever given a wrong absolute time silently.
	 */
	const struct tank_boot_time_stamp stamp = stamp_of(&bt, 10000U);

	zassert_true(stamp.tk);
	zassert_equal(stamp.t_s, stepped_epoch_ms / 1000U);
}

ZTEST(record_boot_time, test_warning_clears_on_a_sync_that_agrees)
{
	struct tank_boot_time bt = bt_for(BOOT_ID_A);
	const uint64_t epoch_ms = 1700000000000ULL;

	zassert_equal(tank_boot_time_record_sync(&bt, 0U, epoch_ms), 0);
	zassert_equal(tank_boot_time_record_sync(&bt, 1000U, epoch_ms - 5000U), 0);
	zassert_true(tank_boot_time_warning_active(&bt));

	/* A later sync that agrees with the (now corrected) offset within
	 * the limit clears the warning.
	 */
	zassert_equal(tank_boot_time_record_sync(&bt, 2000U, epoch_ms - 5000U + 2000U), 0);
	zassert_false(tank_boot_time_warning_active(&bt));
}

ZTEST(record_boot_time, test_drift_within_limit_does_not_warn)
{
	struct tank_boot_time bt = bt_for(BOOT_ID_A);
	const uint64_t epoch_ms = 1700000000000ULL;

	zassert_equal(tank_boot_time_record_sync(&bt, 0U, epoch_ms), 0);
	/* 500 ms of drift, under the 1000 ms limit. */
	zassert_equal(tank_boot_time_record_sync(&bt, 1000U, epoch_ms + 500U), 0);
	zassert_false(tank_boot_time_warning_active(&bt));
}

ZTEST(record_boot_time, test_boot_id_changes_across_a_power_cycle)
{
	struct tank_boot_time bt_a = bt_for(BOOT_ID_A);
	struct tank_boot_time bt_b = bt_for(BOOT_ID_B);

	const struct tank_boot_time_stamp stamp_a = stamp_of(&bt_a, 0U);
	const struct tank_boot_time_stamp stamp_b = stamp_of(&bt_b, 0U);

	zassert_mem_equal(stamp_a.boot_id, BOOT_ID_A, TANK_BOOT_ID_LEN);
	zassert_mem_equal(stamp_b.boot_id, BOOT_ID_B, TANK_BOOT_ID_LEN);
	zassert_not_equal(memcmp(stamp_a.boot_id, stamp_b.boot_id, TANK_BOOT_ID_LEN), 0);

	/* A reboot starts without knowledge of the time again, even though
	 * the previous boot had synced.
	 */
	zassert_equal(tank_boot_time_record_sync(&bt_a, 0U, 1700000000000ULL), 0);
	zassert_true(tank_boot_time_known(&bt_a));
	zassert_false(tank_boot_time_known(&bt_b));
}

ZTEST(record_boot_time, test_functions_reject_null_or_uninitialised)
{
	struct tank_boot_time uninitialised = {0};
	struct tank_boot_time_stamp stamp;

	zassert_equal(tank_boot_time_record_sync(NULL, 0U, 0ULL), -EINVAL);
	zassert_equal(tank_boot_time_record_sync(&uninitialised, 0U, 0ULL), -EINVAL);
	zassert_equal(tank_boot_time_record_sync_failure(NULL), -EINVAL);
	zassert_equal(tank_boot_time_record_sync_failure(&uninitialised), -EINVAL);
	zassert_equal(tank_boot_time_stamp(NULL, 0U, &stamp), -EINVAL);
	zassert_equal(tank_boot_time_stamp(&uninitialised, 0U, NULL), -EINVAL);
	zassert_false(tank_boot_time_warning_active(NULL));
	zassert_false(tank_boot_time_known(NULL));
}
