/*
 * ztest suite for the CBOR record encoder (S-044, P1-12).
 *
 * The golden records were produced from the same values by Python cbor2 in
 * the simulator's virtual environment, after validating each one against
 * interfaces/records.cddl with the simulator's schema code:
 *
 *   schema = tanksim.record.default_schema()
 *   schema.validate(record)
 *   cbor2.dumps(record, canonical=True)
 *
 * canonical=True is RFC 8949's deterministic encoding, which is what the
 * encoder promises, so the bytes must match exactly.
 */

#include <zephyr/ztest.h>

#include <string.h>

#include "link_frame.h"
#include "reading_quality.h"
#include "record_cbor.h"

BUILD_ASSERT(TANK_RECORD_CBOR_MAX <= TANK_LINK_PAYLOAD_MAX,
	     "a worst-case scan record must fit in one RECORD frame");

#define DEV "TANK-0001"
#define T_KNOWN 1795651200ULL
#define READINGS 3U

/* clang-format off */
static const uint8_t golden_scan_time_known[] = {
	0xa9, 0x61, 0x72, 0x83, 0xa4, 0x61, 0x71, 0x00, 0x62, 0x69, 0x64, 0x19, 0x03, 0xe9, 0x63,
	0x61, 0x67, 0x65, 0x14, 0x63, 0x76, 0x61, 0x6c, 0x19, 0x2e, 0xe0, 0xa4, 0x61, 0x71, 0x00,
	0x62, 0x69, 0x64, 0x19, 0x07, 0xd1, 0x63, 0x61, 0x67, 0x65, 0x18, 0xfa, 0x63, 0x76, 0x61,
	0x6c, 0x38, 0x95, 0xa4, 0x61, 0x71, 0x00, 0x62, 0x69, 0x64, 0x19, 0x0b, 0xb9, 0x63, 0x61,
	0x67, 0x65, 0x00, 0x63, 0x76, 0x61, 0x6c, 0x01, 0x61, 0x74, 0x1a, 0x6b, 0x07, 0x76, 0x80,
	0x61, 0x76, 0x01, 0x62, 0x73, 0x6c, 0x01, 0x62, 0x74, 0x6b, 0xf5, 0x62, 0x75, 0x70, 0x19,
	0xa4, 0x10, 0x63, 0x64, 0x65, 0x76, 0x69, 0x54, 0x41, 0x4e, 0x4b, 0x2d, 0x30, 0x30, 0x30,
	0x31, 0x63, 0x73, 0x65, 0x71, 0x18, 0x2a, 0x64, 0x62, 0x6f, 0x6f, 0x74, 0x50, 0x01, 0x02,
	0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f, 0x10,
};

static const uint8_t golden_scan_no_time[] = {
	0xa8, 0x61, 0x72, 0x83, 0xa4, 0x61, 0x71, 0x00, 0x62, 0x69, 0x64, 0x19, 0x03, 0xe9, 0x63,
	0x61, 0x67, 0x65, 0x14, 0x63, 0x76, 0x61, 0x6c, 0x19, 0x2e, 0xe0, 0xa4, 0x61, 0x71, 0x00,
	0x62, 0x69, 0x64, 0x19, 0x07, 0xd1, 0x63, 0x61, 0x67, 0x65, 0x18, 0xfa, 0x63, 0x76, 0x61,
	0x6c, 0x38, 0x95, 0xa4, 0x61, 0x71, 0x00, 0x62, 0x69, 0x64, 0x19, 0x0b, 0xb9, 0x63, 0x61,
	0x67, 0x65, 0x00, 0x63, 0x76, 0x61, 0x6c, 0x01, 0x61, 0x76, 0x01, 0x62, 0x73, 0x6c, 0x01,
	0x62, 0x74, 0x6b, 0xf4, 0x62, 0x75, 0x70, 0x19, 0x0b, 0xb8, 0x63, 0x64, 0x65, 0x76, 0x69,
	0x54, 0x41, 0x4e, 0x4b, 0x2d, 0x30, 0x30, 0x30, 0x31, 0x63, 0x73, 0x65, 0x71, 0x03, 0x64,
	0x62, 0x6f, 0x6f, 0x74, 0x50, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a,
	0x0b, 0x0c, 0x0d, 0x0e, 0x0f, 0x10,
};

static const uint8_t golden_scan_fault[] = {
	0xa8, 0x61, 0x72, 0x81, 0xa3, 0x61, 0x71, 0x03, 0x62, 0x69, 0x64, 0x19, 0x07, 0xd3, 0x63,
	0x61, 0x67, 0x65, 0x19, 0x03, 0xe8, 0x61, 0x76, 0x01, 0x62, 0x73, 0x6c, 0x01, 0x62, 0x74,
	0x6b, 0xf4, 0x62, 0x75, 0x70, 0x19, 0x1b, 0x58, 0x63, 0x64, 0x65, 0x76, 0x69, 0x54, 0x41,
	0x4e, 0x4b, 0x2d, 0x30, 0x30, 0x30, 0x31, 0x63, 0x73, 0x65, 0x71, 0x07, 0x64, 0x62, 0x6f,
	0x6f, 0x74, 0x50, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c,
	0x0d, 0x0e, 0x0f, 0x10,
};

static const uint8_t golden_gap[] = {
	0xa3, 0x61, 0x76, 0x01, 0x63, 0x64, 0x65, 0x76, 0x69, 0x54, 0x41, 0x4e, 0x4b, 0x2d, 0x30,
	0x30, 0x30, 0x31, 0x63, 0x67, 0x61, 0x70, 0xa3, 0x64, 0x6c, 0x61, 0x73, 0x74, 0xa5, 0x61,
	0x74, 0x1a, 0x6b, 0x07, 0x76, 0xe4, 0x62, 0x74, 0x6b, 0xf5, 0x62, 0x75, 0x70, 0x19, 0x07,
	0xd0, 0x63, 0x73, 0x65, 0x71, 0x02, 0x64, 0x62, 0x6f, 0x6f, 0x74, 0x50, 0x11, 0x12, 0x13,
	0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x64, 0x6c,
	0x6f, 0x73, 0x74, 0x05, 0x65, 0x66, 0x69, 0x72, 0x73, 0x74, 0xa4, 0x62, 0x74, 0x6b, 0xf4,
	0x62, 0x75, 0x70, 0x19, 0x27, 0x10, 0x63, 0x73, 0x65, 0x71, 0x0a, 0x64, 0x62, 0x6f, 0x6f,
	0x74, 0x50, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d,
	0x0e, 0x0f, 0x10,
};
/* clang-format on */

static const uint8_t key_val[] = {0x63, 'v', 'a', 'l'};
static const uint8_t key_t[] = {0x61, 't'};

static uint8_t buf[TANK_RECORD_CBOR_MAX];

static void fill_boot(uint8_t *boot, uint8_t first)
{
	for (uint8_t i = 0U; i < TANK_BOOT_ID_LEN; i++) {
		boot[i] = (uint8_t)(first + i);
	}
}

static void set_reading(struct tank_scan_reading *r, uint16_t id, uint8_t q, uint32_t age,
			bool has_val, int32_t val)
{
	r->id = id;
	r->q = q;
	r->age_ms = age;
	r->has_val = has_val;
	r->val = val;
}

/* The three-reading scan of the golden records. */
static void make_scan(struct tank_scan *s, bool tk)
{
	memset(s, 0, sizeof(*s));
	fill_boot(s->boot_id, 1U);
	s->sl = 1U;
	s->seq = tk ? 42U : 3U;
	s->up_ms = tk ? 42000U : 3000U;
	s->tk = tk;
	s->t_s = tk ? T_KNOWN : 0U;
	s->count = READINGS;
	set_reading(&s->r[0], 1001U, TANK_QUALITY_GOOD, 20U, true, 12000);
	set_reading(&s->r[1], 2001U, TANK_QUALITY_GOOD, 250U, true, -150);
	set_reading(&s->r[2], 3001U, TANK_QUALITY_GOOD, 0U, true, 1);
}

static void make_gap(struct tank_log_gap *g)
{
	memset(g, 0, sizeof(*g));
	g->lost = 5U;
	fill_boot(g->first.boot_id, 0x01U);
	g->first.seq = 10U;
	g->first.up_ms = 10000U;
	fill_boot(g->last.boot_id, 0x11U);
	g->last.seq = 2U;
	g->last.up_ms = 2000U;
	g->last.tk = true;
	g->last.t_s = T_KNOWN + 100U;
}

/* Offset just past the first occurrence of key in out, or 0 if absent. */
static size_t after_key(const uint8_t *out, size_t len, const uint8_t *key, size_t key_len)
{
	for (size_t i = 0U; i + key_len <= len; i++) {
		if (memcmp(&out[i], key, key_len) == 0) {
			return i + key_len;
		}
	}
	return 0U;
}

static void assert_encodes(size_t len, const uint8_t *golden, size_t golden_len)
{
	zassert_equal(len, golden_len, "length %zu, expected %zu", len, golden_len);
	zassert_mem_equal(buf, golden, golden_len);
}

ZTEST(record_cbor, test_scan_time_known)
{
	struct tank_scan s;

	make_scan(&s, true);
	size_t len = tank_record_cbor_encode_scan(DEV, &s, buf, sizeof(buf));

	assert_encodes(len, golden_scan_time_known, sizeof(golden_scan_time_known));
}

ZTEST(record_cbor, test_scan_without_time_has_no_t)
{
	struct tank_scan s;

	make_scan(&s, false);
	/* A stale t_s must not leak into a record whose time is not known. */
	s.t_s = T_KNOWN;
	size_t len = tank_record_cbor_encode_scan(DEV, &s, buf, sizeof(buf));

	assert_encodes(len, golden_scan_no_time, sizeof(golden_scan_no_time));
	zassert_equal(after_key(buf, len, key_t, sizeof(key_t)), 0U);
}

ZTEST(record_cbor, test_fault_reading_has_no_val)
{
	struct tank_scan s;

	make_scan(&s, false);
	s.seq = 7U;
	s.up_ms = 7000U;
	s.count = 1U;
	set_reading(&s.r[0], 2003U, TANK_QUALITY_FAULT, 1000U, false, 0);
	size_t len = tank_record_cbor_encode_scan(DEV, &s, buf, sizeof(buf));

	assert_encodes(len, golden_scan_fault, sizeof(golden_scan_fault));
	zassert_equal(after_key(buf, len, key_val, sizeof(key_val)), 0U);
}

ZTEST(record_cbor, test_gap_record)
{
	struct tank_log_gap g;

	make_gap(&g);
	/* A stale t_s on the first mark must not be written: its tk is false. */
	g.first.t_s = T_KNOWN;
	size_t len = tank_record_cbor_encode_gap(DEV, &g, buf, sizeof(buf));

	assert_encodes(len, golden_gap, sizeof(golden_gap));
}

ZTEST(record_cbor, test_item_dispatch)
{
	static struct tank_log_item item;

	make_scan(&item.scan, true);
	make_gap(&item.gap);
	item.kind = TANK_LOG_ITEM_SCAN;
	assert_encodes(tank_record_cbor_encode_item(DEV, &item, buf, sizeof(buf)),
		       golden_scan_time_known, sizeof(golden_scan_time_known));
	item.kind = TANK_LOG_ITEM_GAP;
	assert_encodes(tank_record_cbor_encode_item(DEV, &item, buf, sizeof(buf)), golden_gap,
		       sizeof(golden_gap));
	item.kind = (enum tank_log_item_kind)99;
	zassert_equal(tank_record_cbor_encode_item(DEV, &item, buf, sizeof(buf)), 0U);
	zassert_equal(tank_record_cbor_encode_item(DEV, NULL, buf, sizeof(buf)), 0U);
}

ZTEST(record_cbor, test_deterministic)
{
	static uint8_t again[TANK_RECORD_CBOR_MAX];
	struct tank_scan s;

	make_scan(&s, true);
	size_t len = tank_record_cbor_encode_scan(DEV, &s, buf, sizeof(buf));
	size_t len2 = tank_record_cbor_encode_scan(DEV, &s, again, sizeof(again));

	zassert_true(len > 0U);
	zassert_equal(len, len2);
	zassert_mem_equal(buf, again, len);
}

/* Encode a one-reading scan with this value and check the bytes after "val". */
static void assert_val_encoding(int32_t val, const uint8_t *expect, size_t expect_len)
{
	struct tank_scan s;

	make_scan(&s, false);
	s.count = 1U;
	s.r[0].val = val;
	size_t len = tank_record_cbor_encode_scan(DEV, &s, buf, sizeof(buf));
	size_t at = after_key(buf, len, key_val, sizeof(key_val));

	zassert_true(at > 0U, "no val for %d", val);
	zassert_mem_equal(&buf[at], expect, expect_len, "val %d", val);
}

ZTEST(record_cbor, test_integer_boundaries)
{
	assert_val_encoding(23, (const uint8_t[]){0x17}, 1U);
	assert_val_encoding(24, (const uint8_t[]){0x18, 0x18}, 2U);
	assert_val_encoding(255, (const uint8_t[]){0x18, 0xff}, 2U);
	assert_val_encoding(256, (const uint8_t[]){0x19, 0x01, 0x00}, 3U);
	assert_val_encoding(65535, (const uint8_t[]){0x19, 0xff, 0xff}, 3U);
	assert_val_encoding(65536, (const uint8_t[]){0x1a, 0x00, 0x01, 0x00, 0x00}, 5U);
	assert_val_encoding(INT32_MAX, (const uint8_t[]){0x1a, 0x7f, 0xff, 0xff, 0xff}, 5U);
	assert_val_encoding(-1, (const uint8_t[]){0x20}, 1U);
	assert_val_encoding(-25, (const uint8_t[]){0x38, 0x18}, 2U);
	assert_val_encoding(INT32_MIN, (const uint8_t[]){0x3a, 0x7f, 0xff, 0xff, 0xff}, 5U);
}

ZTEST(record_cbor, test_wide_time_and_age)
{
	static const uint8_t t_expect[] = {0x1b, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00};
	static const uint8_t key_age[] = {0x63, 'a', 'g', 'e'};
	static const uint8_t age_expect[] = {0x1a, 0xff, 0xff, 0xff, 0xff};
	struct tank_scan s;

	make_scan(&s, true);
	s.t_s = 1ULL << 32U;
	s.r[0].age_ms = UINT32_MAX;
	size_t len = tank_record_cbor_encode_scan(DEV, &s, buf, sizeof(buf));

	zassert_mem_equal(&buf[after_key(buf, len, key_t, sizeof(key_t))], t_expect,
			  sizeof(t_expect));
	zassert_mem_equal(&buf[after_key(buf, len, key_age, sizeof(key_age))], age_expect,
			  sizeof(age_expect));
}

ZTEST(record_cbor, test_invalid_scans_refused)
{
	static const char long_id[] = "0123456789abcdef0123456789abcdefX";
	struct tank_scan s;

	make_scan(&s, true);
	zassert_equal(tank_record_cbor_encode_scan(NULL, &s, buf, sizeof(buf)), 0U);
	zassert_equal(tank_record_cbor_encode_scan("", &s, buf, sizeof(buf)), 0U);
	zassert_equal(tank_record_cbor_encode_scan(long_id, &s, buf, sizeof(buf)), 0U);
	zassert_equal(tank_record_cbor_encode_scan(DEV, NULL, buf, sizeof(buf)), 0U);
	zassert_equal(tank_record_cbor_encode_scan(DEV, &s, NULL, sizeof(buf)), 0U);

	s.count = 0U;
	zassert_equal(tank_record_cbor_encode_scan(DEV, &s, buf, sizeof(buf)), 0U, "no readings");
	s.count = TANK_SCAN_MAX_READINGS + 1U;
	zassert_equal(tank_record_cbor_encode_scan(DEV, &s, buf, sizeof(buf)), 0U, "too many");

	make_scan(&s, true);
	s.r[1].q = TANK_QUALITY_UNCONFIGURED + 1U;
	zassert_equal(tank_record_cbor_encode_scan(DEV, &s, buf, sizeof(buf)), 0U, "bad quality");

	make_scan(&s, true);
	s.r[2].q = TANK_QUALITY_FAULT;
	zassert_equal(tank_record_cbor_encode_scan(DEV, &s, buf, sizeof(buf)), 0U, "fault val");
	s.r[2].q = TANK_QUALITY_UNCONFIGURED;
	zassert_equal(tank_record_cbor_encode_scan(DEV, &s, buf, sizeof(buf)), 0U, "unconf val");
}

ZTEST(record_cbor, test_invalid_gaps_refused)
{
	struct tank_log_gap g;

	make_gap(&g);
	zassert_equal(tank_record_cbor_encode_gap("", &g, buf, sizeof(buf)), 0U);
	zassert_equal(tank_record_cbor_encode_gap(DEV, NULL, buf, sizeof(buf)), 0U);
	zassert_equal(tank_record_cbor_encode_gap(DEV, &g, NULL, sizeof(buf)), 0U);
	g.lost = 0U;
	zassert_equal(tank_record_cbor_encode_gap(DEV, &g, buf, sizeof(buf)), 0U, "nothing lost");
}

ZTEST(record_cbor, test_every_short_buffer_refused)
{
	struct tank_scan s;
	struct tank_log_gap g;

	make_scan(&s, true);
	make_gap(&g);
	for (size_t cap = 0U; cap < sizeof(golden_scan_time_known); cap++) {
		zassert_equal(tank_record_cbor_encode_scan(DEV, &s, buf, cap), 0U, "cap %zu", cap);
	}
	for (size_t cap = 0U; cap < sizeof(golden_gap); cap++) {
		zassert_equal(tank_record_cbor_encode_gap(DEV, &g, buf, cap), 0U, "cap %zu", cap);
	}
}

/* Every integer at its widest and the longest device id. */
ZTEST(record_cbor, test_worst_case_fits)
{
	static const char max_id[] = "0123456789abcdef0123456789abcdef";
	static struct tank_scan s;

	BUILD_ASSERT(sizeof(max_id) - 1U == TANK_RECORD_DEV_ID_MAX);
	make_scan(&s, true);
	s.sl = UINT32_MAX;
	s.seq = UINT32_MAX;
	s.up_ms = UINT32_MAX;
	s.t_s = UINT64_MAX;
	s.count = TANK_SCAN_MAX_READINGS;
	for (uint8_t i = 0U; i < TANK_SCAN_MAX_READINGS; i++) {
		set_reading(&s.r[i], UINT16_MAX, TANK_QUALITY_OUT_OF_RANGE, UINT32_MAX, true,
			    INT32_MIN);
	}
	size_t len = tank_record_cbor_encode_scan(max_id, &s, buf, sizeof(buf));

	zassert_equal(len, TANK_RECORD_CBOR_MAX, "worst case is %zu bytes", len);
}

ZTEST_SUITE(record_cbor, NULL, NULL, NULL, NULL, NULL);
