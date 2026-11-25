/*
 * Append-only flash log: the outage buffer (S-039, P1-14).
 * See flash_log.h for the design.
 */

#include "flash_log.h"

#include <errno.h>
#include <string.h>

#include <zephyr/drivers/flash.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/crc.h>
#include <zephyr/sys/util.h>

#define FRAME_HDR 3U
#define FRAME_CRC 2U
#define FRAME_EXTRA (FRAME_HDR + FRAME_CRC)
#define CRC_SEED 0xFFFFU
#define ERASED_BYTE 0xFFU
#define MIN_SECTORS 2U
#define SECTOR_PAYLD 12U
#define GAP_PAYLD 4U
#define ACK_PAYLD 8U

enum entry_type {
	ENTRY_SECTOR = 0x01,
	ENTRY_FULL = 0x02,
	ENTRY_DELTA = 0x03,
	ENTRY_GAP = 0x04,
	ENTRY_ACK = 0x05,
};

struct frame {
	uint8_t type;
	size_t len;
	const uint8_t *payload;
};

static size_t sector_addr(const struct tank_flash_log *log, uint32_t seq)
{
	return log->cfg.offset + (size_t)(seq % log->sector_count) * log->cfg.sector_size;
}

static uint64_t pos_of(const struct tank_flash_log *log, uint32_t seq, size_t off)
{
	return (uint64_t)seq * log->cfg.sector_size + off;
}

static uint64_t write_pos(const struct tank_flash_log *log)
{
	return pos_of(log, log->head_seq, log->head_off);
}

static bool fits(const struct tank_flash_log *log, size_t payload_len)
{
	return log->head_off + FRAME_EXTRA + payload_len <= log->cfg.sector_size;
}

/* Frame the payload already placed at log->frame + FRAME_HDR and write it. */
static int write_frame(struct tank_flash_log *log, uint8_t type, size_t len)
{
	uint8_t *f = log->frame;
	int rc;

	f[0] = type;
	sys_put_le16((uint16_t)len, &f[1]);
	sys_put_le16(crc16_ccitt(CRC_SEED, f, FRAME_HDR + len), &f[FRAME_HDR + len]);
	rc = flash_write(log->cfg.flash, sector_addr(log, log->head_seq) + log->head_off, f,
			 len + FRAME_EXTRA);
	if (rc == 0) {
		log->head_off += len + FRAME_EXTRA;
	}
	return rc;
}

/* Returns 0, -ENOENT on erased flash, -EBADMSG on a torn or corrupt entry. */
static int read_frame(struct tank_flash_log *log, uint32_t seq, size_t off, struct frame *out)
{
	uint8_t *f = log->frame;
	size_t len;
	int rc;

	if (off + FRAME_EXTRA > log->cfg.sector_size) {
		return -ENOENT;
	}
	rc = flash_read(log->cfg.flash, sector_addr(log, seq) + off, f, FRAME_HDR);
	if (rc != 0) {
		return rc;
	}
	if (f[0] == ERASED_BYTE) {
		return -ENOENT;
	}
	len = sys_get_le16(&f[1]);
	if (len > TANK_FLASH_LOG_FRAME_MAX - FRAME_EXTRA ||
	    off + FRAME_EXTRA + len > log->cfg.sector_size) {
		return -EBADMSG;
	}
	rc = flash_read(log->cfg.flash, sector_addr(log, seq) + off + FRAME_HDR, &f[FRAME_HDR],
			len + FRAME_CRC);
	if (rc != 0) {
		return rc;
	}
	if (crc16_ccitt(CRC_SEED, f, FRAME_HDR + len) != sys_get_le16(&f[FRAME_HDR + len])) {
		return -EBADMSG;
	}
	*out = (struct frame){.type = f[0], .len = len, .payload = &f[FRAME_HDR]};
	return 0;
}

/* True when the sector for seq starts with its own header; gives its ack. */
static bool sector_header(struct tank_flash_log *log, uint32_t seq, uint64_t *ack)
{
	struct frame fr;

	if (read_frame(log, seq, 0U, &fr) != 0 || fr.type != ENTRY_SECTOR ||
	    fr.len != SECTOR_PAYLD || sys_get_le32(fr.payload) != seq) {
		return false;
	}
	*ack = sys_get_le64(&fr.payload[4]);
	return true;
}

/* Undelivered scans in a sector, plus those its own undelivered gaps lost.
 * *scans gets the first part alone, so lost_scans counts each scan once.
 */
static uint32_t count_lost(struct tank_flash_log *log, uint32_t seq, uint64_t from, uint32_t *scans)
{
	struct frame fr;
	uint32_t n = 0U;
	size_t off = 0U;

	*scans = 0U;

	while (read_frame(log, seq, off, &fr) == 0) {
		bool undelivered = pos_of(log, seq, off) >= from;

		if (undelivered && (fr.type == ENTRY_FULL || fr.type == ENTRY_DELTA)) {
			n++;
			(*scans)++;
		} else if (undelivered && fr.type == ENTRY_GAP && fr.len == GAP_PAYLD) {
			n += sys_get_le32(fr.payload);
		}
		off += fr.len + FRAME_EXTRA;
	}
	return n;
}

/* The ring is full: drop the oldest sector, recording undelivered scans. */
static uint32_t drop_oldest(struct tank_flash_log *log, uint32_t old)
{
	uint64_t old_end = pos_of(log, old + 1U, 0U);
	uint64_t ack;
	uint32_t lost = 0U;
	uint32_t scans;

	if (sector_header(log, old, &ack) && log->ack_pos < old_end) {
		lost = count_lost(log, old, MAX(log->ack_pos, pos_of(log, old, 0U)), &scans);
		log->lost_scans += scans;
		log->ack_pos = old_end;
	}
	if (log->read_pos < old_end) {
		log->read_pos = old_end;
		log->read_prev_valid = false;
	}
	log->tail_pos = MAX(log->tail_pos, old_end);
	return lost;
}

static int open_sector(struct tank_flash_log *log, uint32_t seq)
{
	uint8_t *p = &log->frame[FRAME_HDR];
	int rc = flash_erase(log->cfg.flash, sector_addr(log, seq), log->cfg.sector_size);

	if (rc != 0) {
		return rc;
	}
	log->head_seq = seq;
	log->head_off = 0U;
	log->acks_unpersisted = 0U;
	log->write_prev_valid = false;
	sys_put_le32(seq, p);
	sys_put_le64(log->ack_pos, &p[4]);
	return write_frame(log, ENTRY_SECTOR, SECTOR_PAYLD);
}

static int open_next_sector(struct tank_flash_log *log)
{
	uint32_t next = log->head_seq + 1U;
	uint32_t lost = 0U;
	int rc;

	if (next >= log->sector_count) {
		lost = drop_oldest(log, next - log->sector_count);
	}
	rc = open_sector(log, next);
	if (rc != 0 || lost == 0U) {
		return rc;
	}
	sys_put_le32(lost, &log->frame[FRAME_HDR]);
	return write_frame(log, ENTRY_GAP, GAP_PAYLD);
}

static bool config_valid(const struct tank_flash_log_config *cfg)
{
	return cfg != NULL && cfg->flash != NULL && cfg->sector_size >= TANK_FLASH_LOG_FRAME_MAX &&
	       cfg->offset % cfg->sector_size == 0U && cfg->size % cfg->sector_size == 0U &&
	       cfg->size / cfg->sector_size >= MIN_SECTORS && cfg->full_interval > 0U &&
	       cfg->ack_persist_interval > 0U;
}

static bool find_head(struct tank_flash_log *log, uint64_t *ack)
{
	bool found = false;

	for (uint32_t idx = 0U; idx < log->sector_count; idx++) {
		struct frame fr;
		uint32_t seq;

		if (read_frame(log, idx, 0U, &fr) != 0 || fr.type != ENTRY_SECTOR ||
		    fr.len != SECTOR_PAYLD) {
			continue;
		}
		seq = sys_get_le32(fr.payload);
		if (seq % log->sector_count == idx && (!found || seq > log->head_seq)) {
			log->head_seq = seq;
			*ack = sys_get_le64(&fr.payload[4]);
			found = true;
		}
	}
	return found;
}

static uint32_t find_tail(struct tank_flash_log *log)
{
	uint32_t first =
	    log->head_seq >= log->sector_count - 1U ? log->head_seq - (log->sector_count - 1U) : 0U;
	uint64_t ack;

	for (uint32_t seq = first; seq < log->head_seq; seq++) {
		if (sector_header(log, seq, &ack)) {
			return seq;
		}
	}
	return log->head_seq;
}

/* Find the end of the head sector and the latest persisted ack in it. */
static void scan_head(struct tank_flash_log *log)
{
	struct frame fr;
	size_t off = 0U;
	int rc;

	while ((rc = read_frame(log, log->head_seq, off, &fr)) == 0) {
		if (fr.type == ENTRY_ACK && fr.len == ACK_PAYLD) {
			log->ack_pos = MAX(log->ack_pos, sys_get_le64(fr.payload));
		}
		off += fr.len + FRAME_EXTRA;
	}
	/* A torn entry: nothing more is written in this sector. */
	log->head_off = (rc == -ENOENT) ? off : log->cfg.sector_size;
}

int tank_flash_log_mount(struct tank_flash_log *log, const struct tank_flash_log_config *cfg)
{
	uint64_t ack = 0U;
	int rc = 0;

	if (log == NULL) {
		return -EINVAL;
	}
	log->mounted = false;
	if (!config_valid(cfg)) {
		return -EINVAL;
	}
	memset(log, 0, sizeof(*log));
	log->cfg = *cfg;
	log->sector_count = (uint32_t)(cfg->size / cfg->sector_size);
	if (find_head(log, &ack)) {
		log->tail_pos = pos_of(log, find_tail(log), 0U);
		log->ack_pos = MAX(ack, log->tail_pos);
		scan_head(log);
	} else {
		rc = open_sector(log, 0U);
	}
	log->mounted = (rc == 0);
	tank_flash_log_rewind(log);
	return rc;
}

static size_t encode(struct tank_flash_log *log, const struct tank_scan *scan, uint8_t *type)
{
	uint8_t *p = &log->frame[FRAME_HDR];
	size_t len = 0U;

	if (log->write_prev_valid && log->since_full < log->cfg.full_interval) {
		len = tank_scan_encode_delta(&log->write_prev, scan, p, TANK_SCAN_MAX_ENCODED);
	}
	*type = (len > 0U) ? ENTRY_DELTA : ENTRY_FULL;
	if (len == 0U) {
		len = tank_scan_encode_full(scan, p, TANK_SCAN_MAX_ENCODED);
	}
	return len;
}

int tank_flash_log_append(struct tank_flash_log *log, const struct tank_scan *scan)
{
	uint8_t type;
	size_t len;
	int rc;

	if (log == NULL || scan == NULL || !log->mounted) {
		return -EINVAL;
	}
	len = encode(log, scan, &type);
	if (len > 0U && !fits(log, len)) {
		rc = open_next_sector(log);
		if (rc != 0) {
			return rc;
		}
		len = encode(log, scan, &type);
	}
	if (len == 0U) {
		return -EINVAL;
	}
	rc = write_frame(log, type, len);
	if (rc == 0) {
		log->write_prev = *scan;
		log->write_prev_valid = true;
		log->since_full = (type == ENTRY_FULL) ? 1U : log->since_full + 1U;
	}
	return rc;
}

/* Decode a scan entry, keeping read_prev in step. True when out is valid. */
static bool decode_scan(struct tank_flash_log *log, const struct frame *fr,
			struct tank_log_item *out)
{
	int rc = -EINVAL;

	if (fr->type == ENTRY_FULL) {
		rc = tank_scan_decode_full(fr->payload, fr->len, &out->scan);
	} else if (log->read_prev_valid) {
		rc = tank_scan_decode_delta(&log->read_prev, fr->payload, fr->len, &out->scan);
	}
	log->read_prev_valid = (rc == 0);
	if (rc == 0) {
		log->read_prev = out->scan;
	}
	return rc == 0;
}

/* Turn one entry into an item. True when it should be handed out. */
static bool to_item(struct tank_flash_log *log, const struct frame *fr, struct tank_log_item *out)
{
	if (fr->type == ENTRY_FULL || fr->type == ENTRY_DELTA) {
		out->kind = TANK_LOG_ITEM_SCAN;
		return decode_scan(log, fr, out);
	}
	if (fr->type == ENTRY_GAP && fr->len == GAP_PAYLD) {
		out->kind = TANK_LOG_ITEM_GAP;
		out->lost_scans = sys_get_le32(fr->payload);
		return true;
	}
	return false;
}

int tank_flash_log_read_next(struct tank_flash_log *log, struct tank_log_item *out)
{
	if (log == NULL || out == NULL || !log->mounted) {
		return -EINVAL;
	}
	while (log->read_pos < write_pos(log)) {
		uint32_t seq = (uint32_t)(log->read_pos / log->cfg.sector_size);
		uint64_t start = log->read_pos;
		struct frame fr;
		int rc = read_frame(log, seq, (size_t)(start % log->cfg.sector_size), &fr);

		if (rc == -ENOENT || rc == -EBADMSG) {
			log->read_pos = pos_of(log, seq + 1U, 0U);
			log->read_prev_valid = false;
			continue;
		}
		if (rc != 0) {
			return rc;
		}
		log->read_pos += fr.len + FRAME_EXTRA;
		/* Entries before the delivered position only rebuild delta state. */
		if (to_item(log, &fr, out) && start >= log->ack_pos) {
			out->end_pos = log->read_pos;
			return 0;
		}
	}
	return -ENODATA;
}

int tank_flash_log_ack(struct tank_flash_log *log, uint64_t end_pos)
{
	if (log == NULL || !log->mounted || end_pos > write_pos(log)) {
		return -EINVAL;
	}
	if (end_pos <= log->ack_pos) {
		return 0;
	}
	log->ack_pos = end_pos;
	if (++log->acks_unpersisted < log->cfg.ack_persist_interval) {
		return 0;
	}
	if (!fits(log, ACK_PAYLD)) {
		/* The new sector's header carries the ack. */
		return open_next_sector(log);
	}
	log->acks_unpersisted = 0U;
	sys_put_le64(end_pos, &log->frame[FRAME_HDR]);
	return write_frame(log, ENTRY_ACK, ACK_PAYLD);
}

void tank_flash_log_rewind(struct tank_flash_log *log)
{
	if (log == NULL || !log->mounted) {
		return;
	}
	log->read_pos = MAX(log->ack_pos - log->ack_pos % log->cfg.sector_size, log->tail_pos);
	log->read_prev_valid = false;
}

uint32_t tank_flash_log_lost_scans(const struct tank_flash_log *log)
{
	return (log == NULL) ? 0U : log->lost_scans;
}
