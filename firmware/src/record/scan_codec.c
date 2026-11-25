/*
 * Compact, lossless scan encoding for the flash log (S-039, P1-14).
 * See scan_codec.h for the layout.
 */

#include "scan_codec.h"

#include <errno.h>
#include <string.h>

#define QFLAGS_HAS_VAL 0x80U
#define QFLAGS_Q_MASK 0x7FU
#define FLAGS_TK 0x01U
#define VARINT_MORE 0x80U
#define VARINT_BITS 7U
#define VARINT_MAX_LEN 10U
#define BITS_PER_BYTE 8U
#define BITMAP_MAX ((TANK_SCAN_MAX_READINGS + BITS_PER_BYTE - 1U) / BITS_PER_BYTE)

struct writer {
	uint8_t *buf;
	size_t cap;
	size_t len;
	bool overflow;
};

struct reader {
	const uint8_t *buf;
	size_t len;
	size_t pos;
	bool error;
};

static void put_byte(struct writer *w, uint8_t b)
{
	if (w->len >= w->cap) {
		w->overflow = true;
		return;
	}
	w->buf[w->len++] = b;
}

static void put_uvar(struct writer *w, uint64_t v)
{
	while (v >= VARINT_MORE) {
		put_byte(w, (uint8_t)(v | VARINT_MORE));
		v >>= VARINT_BITS;
	}
	put_byte(w, (uint8_t)v);
}

static void put_svar(struct writer *w, int64_t v)
{
	put_uvar(w, ((uint64_t)v << 1) ^ (uint64_t)(v >> 63));
}

static uint8_t get_byte(struct reader *r)
{
	if (r->pos >= r->len) {
		r->error = true;
		return 0U;
	}
	return r->buf[r->pos++];
}

static uint64_t get_uvar(struct reader *r)
{
	uint64_t v = 0U;

	for (unsigned int i = 0U; i < VARINT_MAX_LEN; i++) {
		uint8_t b = get_byte(r);

		v |= (uint64_t)(b & ~VARINT_MORE) << (VARINT_BITS * i);
		if ((b & VARINT_MORE) == 0U) {
			return v;
		}
	}
	r->error = true;
	return 0U;
}

static int64_t get_svar(struct reader *r)
{
	uint64_t u = get_uvar(r);

	return (int64_t)(u >> 1) ^ -(int64_t)(u & 1U);
}

static bool scan_valid(const struct tank_scan *s)
{
	if (s->count > TANK_SCAN_MAX_READINGS) {
		return false;
	}
	for (uint8_t i = 0U; i < s->count; i++) {
		if (s->r[i].q > QFLAGS_Q_MASK) {
			return false;
		}
	}
	return true;
}

static uint8_t qflags(const struct tank_scan_reading *rd)
{
	return (uint8_t)(rd->q | (rd->has_val ? QFLAGS_HAS_VAL : 0U));
}

static void put_reading_tail(struct writer *w, const struct tank_scan_reading *rd, int32_t base)
{
	put_byte(w, qflags(rd));
	if (rd->has_val) {
		put_svar(w, (int64_t)rd->val - base);
	}
	put_uvar(w, rd->age_ms);
}

static void get_reading_tail(struct reader *r, struct tank_scan_reading *rd, int32_t base)
{
	uint8_t qf = get_byte(r);

	rd->q = qf & QFLAGS_Q_MASK;
	rd->has_val = (qf & QFLAGS_HAS_VAL) != 0U;
	rd->val = rd->has_val ? (int32_t)(get_svar(r) + base) : 0;
	rd->age_ms = (uint32_t)get_uvar(r);
}

size_t tank_scan_encode_full(const struct tank_scan *s, uint8_t *buf, size_t cap)
{
	struct writer w = {.buf = buf, .cap = cap};

	if (s == NULL || buf == NULL || !scan_valid(s)) {
		return 0U;
	}
	for (size_t i = 0U; i < TANK_BOOT_ID_LEN; i++) {
		put_byte(&w, s->boot_id[i]);
	}
	put_uvar(&w, s->sl);
	put_uvar(&w, s->seq);
	put_uvar(&w, s->up_ms);
	put_byte(&w, s->tk ? FLAGS_TK : 0U);
	if (s->tk) {
		put_uvar(&w, s->t_s);
	}
	put_byte(&w, s->count);
	for (uint8_t i = 0U; i < s->count; i++) {
		put_uvar(&w, s->r[i].id);
		put_reading_tail(&w, &s->r[i], 0);
	}
	return w.overflow ? 0U : w.len;
}

bool tank_scan_can_delta(const struct tank_scan *prev, const struct tank_scan *s)
{
	if (prev == NULL || s == NULL || !scan_valid(s) || prev->count != s->count ||
	    prev->sl != s->sl || s->seq < prev->seq || s->up_ms < prev->up_ms ||
	    memcmp(prev->boot_id, s->boot_id, TANK_BOOT_ID_LEN) != 0) {
		return false;
	}
	for (uint8_t i = 0U; i < s->count; i++) {
		if (prev->r[i].id != s->r[i].id) {
			return false;
		}
	}
	return true;
}

static bool meta_changed(const struct tank_scan_reading *a, const struct tank_scan_reading *b)
{
	return a->has_val != b->has_val || a->q != b->q || a->age_ms != b->age_ms;
}

static int32_t delta_base(const struct tank_scan_reading *prev)
{
	return prev->has_val ? prev->val : 0;
}

static bool val_changed(const struct tank_scan_reading *prev, const struct tank_scan_reading *s)
{
	return s->has_val && s->val != delta_base(prev);
}

static int64_t prev_t(const struct tank_scan *prev)
{
	return prev->tk ? (int64_t)prev->t_s : 0;
}

static size_t bitmap_len(uint8_t count)
{
	return ((size_t)count + BITS_PER_BYTE - 1U) / BITS_PER_BYTE;
}

static bool bit_set(const uint8_t *bitmap, uint8_t i)
{
	return (bitmap[i / BITS_PER_BYTE] & (1U << (i % BITS_PER_BYTE))) != 0U;
}

/* Two bitmaps: readings whose quality, presence or age changed, then
 * readings whose value changed. A noisy analogue costs one byte.
 */
static void put_bitmaps(struct writer *w, const struct tank_scan *prev, const struct tank_scan *s)
{
	uint8_t meta[BITMAP_MAX] = {0};
	uint8_t vals[BITMAP_MAX] = {0};

	for (uint8_t i = 0U; i < s->count; i++) {
		uint8_t bit = (uint8_t)(1U << (i % BITS_PER_BYTE));

		meta[i / BITS_PER_BYTE] |= meta_changed(&prev->r[i], &s->r[i]) ? bit : 0U;
		vals[i / BITS_PER_BYTE] |= val_changed(&prev->r[i], &s->r[i]) ? bit : 0U;
	}
	for (size_t i = 0U; i < bitmap_len(s->count); i++) {
		put_byte(w, meta[i]);
	}
	for (size_t i = 0U; i < bitmap_len(s->count); i++) {
		put_byte(w, vals[i]);
	}
}

size_t tank_scan_encode_delta(const struct tank_scan *prev, const struct tank_scan *s, uint8_t *buf,
			      size_t cap)
{
	struct writer w = {.buf = buf, .cap = cap};

	if (buf == NULL || !tank_scan_can_delta(prev, s)) {
		return 0U;
	}
	put_uvar(&w, s->seq - prev->seq);
	put_uvar(&w, s->up_ms - prev->up_ms);
	put_byte(&w, s->tk ? FLAGS_TK : 0U);
	if (s->tk) {
		put_svar(&w, (int64_t)s->t_s - prev_t(prev));
	}
	put_bitmaps(&w, prev, s);
	for (uint8_t i = 0U; i < s->count; i++) {
		if (meta_changed(&prev->r[i], &s->r[i])) {
			put_byte(&w, qflags(&s->r[i]));
			put_uvar(&w, s->r[i].age_ms);
		}
		if (val_changed(&prev->r[i], &s->r[i])) {
			put_svar(&w, (int64_t)s->r[i].val - delta_base(&prev->r[i]));
		}
	}
	return w.overflow ? 0U : w.len;
}

static int finish(const struct reader *r)
{
	return (r->error || r->pos != r->len) ? -EINVAL : 0;
}

int tank_scan_decode_full(const uint8_t *buf, size_t len, struct tank_scan *out)
{
	struct reader r = {.buf = buf, .len = len};

	if (buf == NULL || out == NULL) {
		return -EINVAL;
	}
	memset(out, 0, sizeof(*out));
	for (size_t i = 0U; i < TANK_BOOT_ID_LEN; i++) {
		out->boot_id[i] = get_byte(&r);
	}
	out->sl = (uint32_t)get_uvar(&r);
	out->seq = (uint32_t)get_uvar(&r);
	out->up_ms = (uint32_t)get_uvar(&r);
	out->tk = (get_byte(&r) & FLAGS_TK) != 0U;
	out->t_s = out->tk ? get_uvar(&r) : 0U;
	out->count = get_byte(&r);
	if (out->count > TANK_SCAN_MAX_READINGS) {
		return -EINVAL;
	}
	for (uint8_t i = 0U; i < out->count; i++) {
		out->r[i].id = (uint16_t)get_uvar(&r);
		get_reading_tail(&r, &out->r[i], 0);
	}
	return finish(&r);
}

static void get_delta_reading(struct reader *r, const struct tank_scan_reading *prev,
			      struct tank_scan_reading *out, bool meta, bool val)
{
	if (meta) {
		uint8_t qf = get_byte(r);

		out->q = qf & QFLAGS_Q_MASK;
		out->has_val = (qf & QFLAGS_HAS_VAL) != 0U;
		out->age_ms = (uint32_t)get_uvar(r);
	}
	out->val = out->has_val ? delta_base(prev) : 0;
	if (val) {
		out->val = (int32_t)(get_svar(r) + delta_base(prev));
	}
}

int tank_scan_decode_delta(const struct tank_scan *prev, const uint8_t *buf, size_t len,
			   struct tank_scan *out)
{
	struct reader r = {.buf = buf, .len = len};
	uint8_t meta[BITMAP_MAX] = {0};
	uint8_t vals[BITMAP_MAX] = {0};

	if (prev == NULL || buf == NULL || out == NULL || prev->count > TANK_SCAN_MAX_READINGS) {
		return -EINVAL;
	}
	if (out != prev) {
		*out = *prev;
	}
	out->seq = prev->seq + (uint32_t)get_uvar(&r);
	out->up_ms = prev->up_ms + (uint32_t)get_uvar(&r);
	out->tk = (get_byte(&r) & FLAGS_TK) != 0U;
	out->t_s = out->tk ? (uint64_t)(get_svar(&r) + prev_t(prev)) : 0U;
	for (size_t i = 0U; i < bitmap_len(prev->count); i++) {
		meta[i] = get_byte(&r);
	}
	for (size_t i = 0U; i < bitmap_len(prev->count); i++) {
		vals[i] = get_byte(&r);
	}
	for (uint8_t i = 0U; i < prev->count; i++) {
		get_delta_reading(&r, &prev->r[i], &out->r[i], bit_set(meta, i), bit_set(vals, i));
	}
	return finish(&r);
}
