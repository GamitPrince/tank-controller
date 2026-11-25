/*
 * ztest suite for the flash log's scan encoding (S-039, P1-14).
 *
 * Pure logic: encoding then decoding must give back exactly the scan that
 * went in (lossless, ADR-0004 decision 12), and a typical one-second scan of
 * the 23 Phase 1 signals must delta encode small enough for the capacity
 * calculation in docs/stories/S-039-outage-buffering.md.
 */

#include <zephyr/ztest.h>

#include <errno.h>
#include <string.h>

#include "scan_codec.h"

#define PHASE1_SIGNALS 23U
#define ANALOGUE_SIGNALS 8U
#define TYPICAL_DELTA_MAX 20U
#define UNCHANGED_DELTA_MAX 12U

static uint8_t buf[TANK_SCAN_MAX_ENCODED];

static void make_scan(struct tank_scan *s, uint32_t seq)
{
	memset(s, 0, sizeof(*s));
	for (uint8_t i = 0U; i < TANK_BOOT_ID_LEN; i++) {
		s->boot_id[i] = (uint8_t)(i + 1U);
	}
	s->sl = 1U;
	s->seq = seq;
	s->up_ms = 1000U * seq;
	s->count = PHASE1_SIGNALS;
	for (uint8_t i = 0U; i < PHASE1_SIGNALS; i++) {
		s->r[i].id = (uint16_t)(1001U + i);
		s->r[i].has_val = true;
		s->r[i].val = (i < ANALOGUE_SIGNALS) ? 12000 : 1;
		s->r[i].q = 0U;
		s->r[i].age_ms = 20U;
	}
}

static void assert_scan_equal(const struct tank_scan *a, const struct tank_scan *b)
{
	zassert_mem_equal(a->boot_id, b->boot_id, TANK_BOOT_ID_LEN);
	zassert_equal(a->sl, b->sl);
	zassert_equal(a->seq, b->seq);
	zassert_equal(a->up_ms, b->up_ms);
	zassert_equal(a->tk, b->tk);
	zassert_equal(a->t_s, b->t_s);
	zassert_equal(a->count, b->count);
	for (uint8_t i = 0U; i < a->count; i++) {
		zassert_equal(a->r[i].id, b->r[i].id);
		zassert_equal(a->r[i].has_val, b->r[i].has_val);
		zassert_equal(a->r[i].val, b->r[i].val);
		zassert_equal(a->r[i].q, b->r[i].q);
		zassert_equal(a->r[i].age_ms, b->r[i].age_ms);
	}
}

static void round_trip_delta(const struct tank_scan *prev, const struct tank_scan *s,
			     size_t *len_out)
{
	struct tank_scan out;
	size_t len = tank_scan_encode_delta(prev, s, buf, sizeof(buf));

	zassert_true(len > 0U);
	zassert_ok(tank_scan_decode_delta(prev, buf, len, &out));
	assert_scan_equal(s, &out);
	*len_out = len;
}

ZTEST(scan_codec, test_full_round_trip_keeps_every_field)
{
	struct tank_scan s;
	struct tank_scan out;
	size_t len;

	make_scan(&s, 7U);
	s.tk = true;
	s.t_s = 1795000000U;
	s.r[0].val = -2500;
	s.r[1].has_val = false;
	s.r[1].val = 0;
	s.r[1].q = 3U;
	s.r[2].age_ms = 70000U;
	len = tank_scan_encode_full(&s, buf, sizeof(buf));
	zassert_true(len > 0U);
	zassert_ok(tank_scan_decode_full(buf, len, &out));
	assert_scan_equal(&s, &out);
}

ZTEST(scan_codec, test_delta_round_trip_with_every_kind_of_change)
{
	struct tank_scan prev;
	struct tank_scan s;
	size_t len;

	make_scan(&prev, 1U);
	make_scan(&s, 2U);
	s.tk = true;
	s.t_s = 1795000001U;
	s.r[0].val = 11997;
	s.r[3].q = 2U;
	s.r[4].has_val = false;
	s.r[4].val = 0;
	s.r[4].q = 3U;
	s.r[22].age_ms = 5000U;
	round_trip_delta(&prev, &s, &len);

	prev = s;
	make_scan(&s, 3U);
	s.tk = true;
	s.t_s = 1795000002U;
	round_trip_delta(&prev, &s, &len);
}

ZTEST(scan_codec, test_typical_scan_deltas_fit_the_capacity_estimate)
{
	struct tank_scan prev;
	struct tank_scan s;
	size_t len;

	make_scan(&prev, 1U);
	make_scan(&s, 2U);
	round_trip_delta(&prev, &s, &len);
	zassert_true(len <= UNCHANGED_DELTA_MAX, "unchanged delta %zu B", len);

	/* Every analogue reading moves by a few counts of noise. */
	for (uint8_t i = 0U; i < ANALOGUE_SIGNALS; i++) {
		s.r[i].val += (i % 2U == 0U) ? 3 : -2;
	}
	round_trip_delta(&prev, &s, &len);
	zassert_true(len <= TYPICAL_DELTA_MAX, "noisy delta %zu B", len);
}

ZTEST(scan_codec, test_delta_refused_when_scans_do_not_line_up)
{
	struct tank_scan prev;
	struct tank_scan s;

	make_scan(&prev, 5U);
	make_scan(&s, 4U);
	zassert_false(tank_scan_can_delta(&prev, &s), "seq went backwards");
	make_scan(&s, 6U);
	s.boot_id[0] = 0xAAU;
	zassert_false(tank_scan_can_delta(&prev, &s), "new boot");
	make_scan(&s, 6U);
	s.count = PHASE1_SIGNALS - 1U;
	zassert_false(tank_scan_can_delta(&prev, &s), "different count");
	make_scan(&s, 6U);
	s.r[5].id = 4242U;
	zassert_false(tank_scan_can_delta(&prev, &s), "different ids");
	make_scan(&s, 6U);
	s.sl = 2U;
	zassert_false(tank_scan_can_delta(&prev, &s), "new signal list");
	zassert_equal(tank_scan_encode_delta(&prev, &prev, NULL, sizeof(buf)), 0U);
	zassert_false(tank_scan_can_delta(NULL, &s));
}

ZTEST(scan_codec, test_invalid_scans_and_small_buffers_are_refused)
{
	struct tank_scan s;

	make_scan(&s, 1U);
	zassert_equal(tank_scan_encode_full(&s, buf, 10U), 0U);
	zassert_equal(tank_scan_encode_full(NULL, buf, sizeof(buf)), 0U);
	s.r[0].q = 0x80U;
	zassert_equal(tank_scan_encode_full(&s, buf, sizeof(buf)), 0U);
	make_scan(&s, 1U);
	s.count = TANK_SCAN_MAX_READINGS + 1U;
	zassert_equal(tank_scan_encode_full(&s, buf, sizeof(buf)), 0U);
}

ZTEST(scan_codec, test_malformed_bytes_are_rejected)
{
	struct tank_scan s;
	struct tank_scan out;
	size_t len;
	static const uint8_t endless_varint[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
						 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

	make_scan(&s, 1U);
	len = tank_scan_encode_full(&s, buf, sizeof(buf));
	zassert_equal(tank_scan_decode_full(buf, len - 1U, &out), -EINVAL, "truncated");
	zassert_equal(tank_scan_decode_full(buf, len + 1U, &out), -EINVAL, "trailing byte");
	/* boot id, sl, seq, two-byte up, flags, then count. */
	buf[TANK_BOOT_ID_LEN + 5U] = 0xFFU;
	zassert_equal(tank_scan_decode_full(buf, len, &out), -EINVAL, "count too large");
	zassert_equal(tank_scan_decode_delta(&s, endless_varint, sizeof(endless_varint), &out),
		      -EINVAL);
	zassert_equal(tank_scan_decode_full(NULL, len, &out), -EINVAL);
	zassert_equal(tank_scan_decode_delta(NULL, buf, len, &out), -EINVAL);
}

ZTEST_SUITE(scan_codec, NULL, NULL, NULL, NULL, NULL);
