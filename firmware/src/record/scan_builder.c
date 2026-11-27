/*
 * Build the one-second scan record from the readings (S-058, P1-12).
 * See scan_builder.h for the mapping.
 */

#include "scan_builder.h"

#include <errno.h>
#include <stdbool.h>
#include <string.h>

/* Transmitted units per engineering unit, from the signal list's `scale`. */
#define MICROAMPS_PER_MA 1000.0f
#define CENTI_DEGC_PER_DEGC 100.0f

static int32_t to_scaled(float value, float units_per_unit)
{
	const float scaled = value * units_per_unit;

	return (int32_t)((scaled >= 0.0f) ? (scaled + 0.5f) : (scaled - 0.5f));
}

static void put_measured(struct tank_scan_reading *r, uint16_t id, enum tank_reading_quality q,
			 int32_t scaled, uint32_t age_ms)
{
	r->id = id;
	r->q = (uint8_t)q;
	r->has_val = (q != TANK_QUALITY_FAULT) && (q != TANK_QUALITY_UNCONFIGURED);
	r->val = r->has_val ? scaled : 0;
	r->age_ms = age_ms;
}

static int add_levels(const struct tank_scan_sources *src, uint32_t now_ms, struct tank_scan *out)
{
	struct tank_loop_level_status st;

	for (size_t i = 0U; i < src->level_count; i++) {
		int err = tank_loop_level_status(&src->levels[i], now_ms, &st);

		if (err != 0) {
			return err;
		}
		put_measured(&out->r[out->count++], st.signal_id, st.quality,
			     to_scaled(st.current_ma, MICROAMPS_PER_MA), st.age_ms);
	}
	return 0;
}

static int add_temperatures(const struct tank_scan_sources *src, uint32_t now_ms,
			    struct tank_scan *out)
{
	struct tank_product_temperature_status st;

	for (size_t i = 0U; i < src->temperature_count; i++) {
		int err = tank_product_temperature_status(&src->temperatures[i], now_ms, &st);

		if (err != 0) {
			return err;
		}
		put_measured(&out->r[out->count++], st.signal_id, st.quality,
			     to_scaled(st.temperature_degc, CENTI_DEGC_PER_DEGC), st.age_ms);
	}
	return 0;
}

static int put_contact(struct tank_scan_reading *r, const struct tank_level_switch *sw,
		       uint32_t now_ms)
{
	struct tank_level_switch_status st;
	int err = tank_level_switch_status(sw, now_ms, &st);

	if (err != 0) {
		return err;
	}
	if (st.state == TANK_SWITCH_UNKNOWN) {
		put_measured(r, st.signal_id, TANK_QUALITY_FAULT, 0, 0U);
		return 0;
	}
	put_measured(r, st.signal_id, st.live ? TANK_QUALITY_GOOD : TANK_QUALITY_STALE,
		     (st.state == TANK_SWITCH_ASSERTED) ? 1 : 0, now_ms - sw->confirmed_at_ms);
	return 0;
}

static int add_contacts(const struct tank_scan_sources *src, uint32_t now_ms, struct tank_scan *out)
{
	for (size_t i = 0U; i < src->contact_count; i++) {
		int err = put_contact(&out->r[out->count++], &src->contacts[i], now_ms);

		if (err != 0) {
			return err;
		}
	}
	return 0;
}

static bool sources_valid(const struct tank_scan_sources *src)
{
	const size_t total = src->level_count + src->temperature_count + src->contact_count;

	if ((total == 0U) || (total > TANK_SCAN_MAX_READINGS)) {
		return false;
	}
	return !((src->level_count > 0U && src->levels == NULL) ||
		 (src->temperature_count > 0U && src->temperatures == NULL) ||
		 (src->contact_count > 0U && src->contacts == NULL));
}

static int put_header(const struct tank_boot_time *bt, uint32_t sl, uint32_t seq, uint32_t up_ms,
		      struct tank_scan *out)
{
	struct tank_boot_time_stamp stamp;
	int err = tank_boot_time_stamp(bt, up_ms, &stamp);

	if (err != 0) {
		return err;
	}
	memset(out, 0, sizeof(*out));
	memcpy(out->boot_id, stamp.boot_id, TANK_BOOT_ID_LEN);
	out->sl = sl;
	out->seq = seq;
	out->up_ms = stamp.up_ms;
	out->tk = stamp.tk;
	out->t_s = stamp.t_s;
	return 0;
}

int tank_scan_build(const struct tank_scan_sources *src, const struct tank_boot_time *bt,
		    uint32_t sl, uint32_t seq, uint32_t up_ms, struct tank_scan *out)
{
	int err;

	if ((src == NULL) || (bt == NULL) || (out == NULL) || !sources_valid(src)) {
		return -EINVAL;
	}
	err = put_header(bt, sl, seq, up_ms, out);
	if (err == 0) {
		err = add_levels(src, up_ms, out);
	}
	if (err == 0) {
		err = add_temperatures(src, up_ms, out);
	}
	if (err == 0) {
		err = add_contacts(src, up_ms, out);
	}
	return err;
}

static bool reading_changed(const struct tank_scan_reading *a, const struct tank_scan_reading *b,
			    bool is_contact)
{
	return (a->id != b->id) || (a->q != b->q) || (a->has_val != b->has_val) ||
	       (is_contact && (a->val != b->val));
}

bool tank_scan_prompt_change(const struct tank_scan *prev, const struct tank_scan *s,
			     size_t contact_count)
{
	if ((prev == NULL) || (s == NULL)) {
		return false;
	}
	if ((prev->count != s->count) || (contact_count > s->count)) {
		return true;
	}
	const size_t first_contact = s->count - contact_count;

	for (size_t i = 0U; i < s->count; i++) {
		if (reading_changed(&prev->r[i], &s->r[i], i >= first_contact)) {
			return true;
		}
	}
	return false;
}
