/*
 * ztest suite for the SNTP retry policy and health reporting (S-038, P1-15).
 *
 * The real network call (sntp_client.c) is not linked into this suite (see
 * its header); a fake sync_fn stands in, so the retry policy is tested
 * deterministically with no network.
 */

#include <zephyr/ztest.h>

#include <errno.h>
#include <stdint.h>

#include "boot_time.h"
#include "clock_sync.h"

#define AGREEMENT_LIMIT_MS 1000U
#define RETRY_INTERVAL_MS 5000U

static const uint8_t BOOT_ID[TANK_BOOT_ID_LEN] = {1, 2,	 3,  4,	 5,  6,	 7,  8,
						  9, 10, 11, 12, 13, 14, 15, 16};

struct fake_sync_ctx {
	int result;
	uint64_t epoch_ms;
	int call_count;
};

static int fake_sync(void *ctx_, uint64_t *epoch_ms_out)
{
	struct fake_sync_ctx *ctx = ctx_;

	ctx->call_count++;
	if (ctx->result != 0) {
		return ctx->result;
	}

	*epoch_ms_out = ctx->epoch_ms;
	return 0;
}

static void init_all(struct tank_boot_time *bt, struct tank_clock_sync *cs,
		     struct fake_sync_ctx *ctx)
{
	const struct tank_boot_time_config bt_config = {.agreement_limit_ms = AGREEMENT_LIMIT_MS};
	const struct tank_clock_sync_config cs_config = {.retry_interval_ms = RETRY_INTERVAL_MS};

	ctx->result = 0;
	ctx->epoch_ms = 1700000000000ULL;
	ctx->call_count = 0;

	zassert_equal(tank_boot_time_init(bt, BOOT_ID, &bt_config), 0);
	zassert_equal(tank_clock_sync_init(cs, &cs_config, bt, fake_sync, ctx), 0);
}

ZTEST_SUITE(communications_clock_sync, NULL, NULL, NULL, NULL, NULL);

ZTEST(communications_clock_sync, test_init_rejects_bad_arguments)
{
	struct tank_boot_time bt;
	struct tank_clock_sync cs;
	struct fake_sync_ctx ctx = {0};
	const struct tank_boot_time_config bt_config = {.agreement_limit_ms = AGREEMENT_LIMIT_MS};
	const struct tank_clock_sync_config good_config = {.retry_interval_ms = RETRY_INTERVAL_MS};
	const struct tank_clock_sync_config zero_config = {.retry_interval_ms = 0U};

	zassert_equal(tank_boot_time_init(&bt, BOOT_ID, &bt_config), 0);

	zassert_equal(tank_clock_sync_init(NULL, &good_config, &bt, fake_sync, &ctx), -EINVAL);
	zassert_equal(tank_clock_sync_init(&cs, NULL, &bt, fake_sync, &ctx), -EINVAL);
	zassert_equal(tank_clock_sync_init(&cs, &good_config, NULL, fake_sync, &ctx), -EINVAL);
	zassert_equal(tank_clock_sync_init(&cs, &good_config, &bt, NULL, &ctx), -EINVAL);
	zassert_equal(tank_clock_sync_init(&cs, &zero_config, &bt, fake_sync, &ctx), -EINVAL);
}

ZTEST(communications_clock_sync, test_first_poll_always_attempts)
{
	struct tank_boot_time bt;
	struct tank_clock_sync cs;
	struct fake_sync_ctx ctx;

	init_all(&bt, &cs, &ctx);

	zassert_equal(tank_clock_sync_poll(&cs, 0U), 0);
	zassert_equal(ctx.call_count, 1);
	zassert_true(tank_boot_time_known(&bt));
}

ZTEST(communications_clock_sync, test_no_retry_before_the_interval_elapses)
{
	struct tank_boot_time bt;
	struct tank_clock_sync cs;
	struct fake_sync_ctx ctx;

	init_all(&bt, &cs, &ctx);

	zassert_equal(tank_clock_sync_poll(&cs, 0U), 0);
	zassert_equal(tank_clock_sync_poll(&cs, 1000U), 0);
	zassert_equal(tank_clock_sync_poll(&cs, RETRY_INTERVAL_MS - 1U), 0);
	zassert_equal(ctx.call_count, 1);
}

ZTEST(communications_clock_sync, test_retries_once_the_interval_elapses)
{
	struct tank_boot_time bt;
	struct tank_clock_sync cs;
	struct fake_sync_ctx ctx;

	init_all(&bt, &cs, &ctx);

	zassert_equal(tank_clock_sync_poll(&cs, 0U), 0);
	zassert_equal(tank_clock_sync_poll(&cs, RETRY_INTERVAL_MS), 0);
	zassert_equal(ctx.call_count, 2);
}

ZTEST(communications_clock_sync, test_no_sntp_reachable_at_boot_keeps_polling)
{
	struct tank_boot_time bt;
	struct tank_clock_sync cs;
	struct fake_sync_ctx ctx;

	init_all(&bt, &cs, &ctx);
	ctx.result = -ETIMEDOUT;

	zassert_equal(tank_clock_sync_poll(&cs, 0U), 0);
	zassert_false(tank_boot_time_known(&bt));

	zassert_equal(tank_clock_sync_poll(&cs, RETRY_INTERVAL_MS), 0);
	zassert_false(tank_boot_time_known(&bt));
	zassert_equal(ctx.call_count, 2);

	/* The network comes up on the third attempt. */
	ctx.result = 0;
	zassert_equal(tank_clock_sync_poll(&cs, 2U * RETRY_INTERVAL_MS), 0);
	zassert_true(tank_boot_time_known(&bt));
	zassert_false(tank_boot_time_warning_active(&bt));
}

ZTEST(communications_clock_sync, test_uptime_status_reports_signal_9001)
{
	struct tank_boot_time bt;
	struct tank_clock_sync cs;
	struct fake_sync_ctx ctx;
	struct tank_health_uptime_status status;

	init_all(&bt, &cs, &ctx);

	zassert_equal(tank_clock_sync_uptime_status(&cs, 65000U, &status), 0);
	zassert_equal(status.signal_id, 9001U);
	zassert_equal(status.quality, TANK_QUALITY_GOOD);
	zassert_equal(status.uptime_s, 65U);
}

ZTEST(communications_clock_sync, test_warning_status_reports_signal_9004)
{
	struct tank_boot_time bt;
	struct tank_clock_sync cs;
	struct fake_sync_ctx ctx;
	struct tank_health_clock_sync_warning_status status;

	init_all(&bt, &cs, &ctx);

	zassert_equal(tank_clock_sync_poll(&cs, 0U), 0);
	zassert_equal(tank_clock_sync_warning_status(&cs, &status), 0);
	zassert_equal(status.signal_id, 9004U);
	zassert_equal(status.quality, TANK_QUALITY_GOOD);
	zassert_false(status.warning);

	/* A later sync that disagrees by more than the limit flips it. */
	ctx.epoch_ms -= 5000U;
	zassert_equal(tank_clock_sync_poll(&cs, RETRY_INTERVAL_MS), 0);
	zassert_equal(tank_clock_sync_warning_status(&cs, &status), 0);
	zassert_true(status.warning);
}

ZTEST(communications_clock_sync, test_functions_reject_null_or_uninitialised)
{
	struct tank_clock_sync uninitialised = {0};
	struct tank_health_uptime_status uptime_status;
	struct tank_health_clock_sync_warning_status warning_status;

	zassert_equal(tank_clock_sync_poll(NULL, 0U), -EINVAL);
	zassert_equal(tank_clock_sync_poll(&uninitialised, 0U), -EINVAL);
	zassert_equal(tank_clock_sync_uptime_status(NULL, 0U, &uptime_status), -EINVAL);
	zassert_equal(tank_clock_sync_uptime_status(&uninitialised, 0U, NULL), -EINVAL);
	zassert_equal(tank_clock_sync_warning_status(NULL, &warning_status), -EINVAL);
	zassert_equal(tank_clock_sync_warning_status(&uninitialised, NULL), -EINVAL);
}
