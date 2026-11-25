/*
 * CBOR encoding of scan and gap records (S-044). See record_cbor.h.
 */

#include "record_cbor.h"

#include <stdbool.h>
#include <string.h>

#include "reading_quality.h"

/* RFC 8949 major types, already shifted into the top three bits. */
#define CBOR_UINT 0x00U
#define CBOR_NINT 0x20U
#define CBOR_BSTR 0x40U
#define CBOR_TSTR 0x60U
#define CBOR_ARRAY 0x80U
#define CBOR_MAP 0xA0U
#define CBOR_FALSE 0xF4U
#define CBOR_TRUE 0xF5U

/* Additional-information values for 1, 2, 4 and 8 following bytes. */
#define CBOR_AI_1 24U
#define CBOR_AI_2 25U
#define CBOR_AI_4 26U
#define CBOR_AI_8 27U

/*
 * Every map below writes its keys in core deterministic order: shorter keys
 * first, then bytewise, which for these short text keys is the order of the
 * encoded key bytes.
 */
#define SCAN_KEYS_NO_T 8U
#define LOST_SCAN_KEYS_NO_T 4U
#define READING_KEYS_NO_VAL 3U
#define GAP_RECORD_KEYS 3U
#define GAP_KEYS 3U

struct writer {
	uint8_t *buf;
	size_t cap;
	size_t len;
	bool ok;
};

static void put_byte(struct writer *w, uint8_t b)
{
	if (w->len >= w->cap) {
		w->ok = false;
		return;
	}
	w->buf[w->len++] = b;
}

static void put_bytes(struct writer *w, const uint8_t *p, size_t n)
{
	if (n > w->cap - w->len) {
		w->ok = false;
		return;
	}
	memcpy(&w->buf[w->len], p, n);
	w->len += n;
}

/* Major type plus argument in shortest form. */
static void put_head(struct writer *w, uint8_t major, uint64_t arg)
{
	unsigned int bytes;

	if (arg < CBOR_AI_1) {
		put_byte(w, (uint8_t)(major | arg));
		return;
	}
	if (arg <= UINT8_MAX) {
		put_byte(w, (uint8_t)(major | CBOR_AI_1));
		bytes = 1U;
	} else if (arg <= UINT16_MAX) {
		put_byte(w, (uint8_t)(major | CBOR_AI_2));
		bytes = 2U;
	} else if (arg <= UINT32_MAX) {
		put_byte(w, (uint8_t)(major | CBOR_AI_4));
		bytes = 4U;
	} else {
		put_byte(w, (uint8_t)(major | CBOR_AI_8));
		bytes = 8U;
	}
	while (bytes > 0U) {
		bytes--;
		put_byte(w, (uint8_t)(arg >> (8U * bytes)));
	}
}

static void put_int(struct writer *w, int32_t v)
{
	if (v >= 0) {
		put_head(w, CBOR_UINT, (uint64_t)v);
	} else {
		/* -1 - v without overflow for INT32_MIN. */
		put_head(w, CBOR_NINT, (uint64_t)(-(int64_t)v - 1));
	}
}

static void put_key(struct writer *w, const char *key)
{
	size_t n = strlen(key);

	put_head(w, CBOR_TSTR, n);
	put_bytes(w, (const uint8_t *)key, n);
}

static void put_bool(struct writer *w, bool b)
{
	put_byte(w, b ? CBOR_TRUE : CBOR_FALSE);
}

static size_t dev_id_len(const char *dev_id)
{
	size_t n = 0U;

	while (n <= TANK_RECORD_DEV_ID_MAX && dev_id[n] != '\0') {
		n++;
	}
	return n;
}

static bool dev_id_valid(const char *dev_id)
{
	if (dev_id == NULL) {
		return false;
	}
	size_t n = dev_id_len(dev_id);

	return n > 0U && n <= TANK_RECORD_DEV_ID_MAX;
}

static void put_dev(struct writer *w, const char *dev_id)
{
	size_t n = dev_id_len(dev_id);

	put_key(w, "dev");
	put_head(w, CBOR_TSTR, n);
	put_bytes(w, (const uint8_t *)dev_id, n);
}

static void put_boot(struct writer *w, const uint8_t *boot_id)
{
	put_key(w, "boot");
	put_head(w, CBOR_BSTR, TANK_BOOT_ID_LEN);
	put_bytes(w, boot_id, TANK_BOOT_ID_LEN);
}

static bool reading_valid(const struct tank_scan_reading *r)
{
	if (r->q > TANK_QUALITY_UNCONFIGURED) {
		return false;
	}
	bool no_value = r->q == TANK_QUALITY_FAULT || r->q == TANK_QUALITY_UNCONFIGURED;

	return !(no_value && r->has_val);
}

static bool scan_valid(const struct tank_scan *s)
{
	if (s->count == 0U || s->count > TANK_SCAN_MAX_READINGS) {
		return false;
	}
	for (uint8_t i = 0U; i < s->count; i++) {
		if (!reading_valid(&s->r[i])) {
			return false;
		}
	}
	return true;
}

/* reading = { q, id, age, ? val } in deterministic key order. */
static void put_reading(struct writer *w, const struct tank_scan_reading *r)
{
	put_head(w, CBOR_MAP, READING_KEYS_NO_VAL + (r->has_val ? 1U : 0U));
	put_key(w, "q");
	put_head(w, CBOR_UINT, r->q);
	put_key(w, "id");
	put_head(w, CBOR_UINT, r->id);
	put_key(w, "age");
	put_head(w, CBOR_UINT, r->age_ms);
	if (r->has_val) {
		put_key(w, "val");
		put_int(w, r->val);
	}
}

size_t tank_record_cbor_encode_scan(const char *dev_id, const struct tank_scan *scan, uint8_t *buf,
				    size_t cap)
{
	if (!dev_id_valid(dev_id) || scan == NULL || buf == NULL || !scan_valid(scan)) {
		return 0U;
	}
	struct writer w = {.buf = buf, .cap = cap, .len = 0U, .ok = true};

	/* Keys: r t v sl tk up dev seq boot. */
	put_head(&w, CBOR_MAP, SCAN_KEYS_NO_T + (scan->tk ? 1U : 0U));
	put_key(&w, "r");
	put_head(&w, CBOR_ARRAY, scan->count);
	for (uint8_t i = 0U; i < scan->count; i++) {
		put_reading(&w, &scan->r[i]);
	}
	if (scan->tk) {
		put_key(&w, "t");
		put_head(&w, CBOR_UINT, scan->t_s);
	}
	put_key(&w, "v");
	put_head(&w, CBOR_UINT, TANK_RECORD_SCHEMA_VERSION);
	put_key(&w, "sl");
	put_head(&w, CBOR_UINT, scan->sl);
	put_key(&w, "tk");
	put_bool(&w, scan->tk);
	put_key(&w, "up");
	put_head(&w, CBOR_UINT, scan->up_ms);
	put_dev(&w, dev_id);
	put_key(&w, "seq");
	put_head(&w, CBOR_UINT, scan->seq);
	put_boot(&w, scan->boot_id);
	return w.ok ? w.len : 0U;
}

/* lost-scan = { t?, tk, up, seq, boot } in deterministic key order. */
static void put_lost_scan(struct writer *w, const struct tank_log_mark *m)
{
	put_head(w, CBOR_MAP, LOST_SCAN_KEYS_NO_T + (m->tk ? 1U : 0U));
	if (m->tk) {
		put_key(w, "t");
		put_head(w, CBOR_UINT, m->t_s);
	}
	put_key(w, "tk");
	put_bool(w, m->tk);
	put_key(w, "up");
	put_head(w, CBOR_UINT, m->up_ms);
	put_key(w, "seq");
	put_head(w, CBOR_UINT, m->seq);
	put_boot(w, m->boot_id);
}

size_t tank_record_cbor_encode_gap(const char *dev_id, const struct tank_log_gap *gap, uint8_t *buf,
				   size_t cap)
{
	if (!dev_id_valid(dev_id) || gap == NULL || buf == NULL || gap->lost == 0U) {
		return 0U;
	}
	struct writer w = {.buf = buf, .cap = cap, .len = 0U, .ok = true};

	/* Keys: v dev gap; inside gap: last lost first. */
	put_head(&w, CBOR_MAP, GAP_RECORD_KEYS);
	put_key(&w, "v");
	put_head(&w, CBOR_UINT, TANK_RECORD_SCHEMA_VERSION);
	put_dev(&w, dev_id);
	put_key(&w, "gap");
	put_head(&w, CBOR_MAP, GAP_KEYS);
	put_key(&w, "last");
	put_lost_scan(&w, &gap->last);
	put_key(&w, "lost");
	put_head(&w, CBOR_UINT, gap->lost);
	put_key(&w, "first");
	put_lost_scan(&w, &gap->first);
	return w.ok ? w.len : 0U;
}

size_t tank_record_cbor_encode_item(const char *dev_id, const struct tank_log_item *item,
				    uint8_t *buf, size_t cap)
{
	if (item == NULL) {
		return 0U;
	}
	switch (item->kind) {
	case TANK_LOG_ITEM_SCAN:
		return tank_record_cbor_encode_scan(dev_id, &item->scan, buf, cap);
	case TANK_LOG_ITEM_GAP:
		return tank_record_cbor_encode_gap(dev_id, &item->gap, buf, cap);
	default:
		return 0U;
	}
}
