/*
 * Append-only flash log: the outage buffer (S-039, P1-14).
 *
 * ADR-0004 decisions 3 and 12, as resolved by the tech lead on 2026-11-25
 * (docs/stories/S-039-outage-buffering.md):
 * - Always log first. Every scan is appended when it is made, forwarded from
 *   here, and only counts as delivered once tank_flash_log_ack() is called
 *   after a cloud acknowledgement. There is no buffer-start threshold.
 * - The log is a ring of erase sectors over the whole partition. When the
 *   ring is full the oldest sector is erased; if it still held undelivered
 *   scans, a gap entry recording how many were lost, and the first and last
 *   of them, is written and later forwarded like a scan (S-040). A dropped
 *   sector's own undelivered gap entries are carried into the new one, so
 *   neither the count nor the start of the hole is ever lost.
 * - Delta encoded (scan_codec.h). Every sector starts with a full scan, so
 *   dropping a sector never orphans the deltas after it.
 * - Each entry is framed as type, length, payload and CRC-16, and is only
 *   ever written to erased flash. A power cut mid-write leaves a torn entry
 *   that fails its CRC; mounting stops reading that sector there and writes
 *   on in a fresh one, so every entry written before the cut survives.
 *
 * Positions are 64-bit logical offsets: sector sequence number times sector
 * size plus the offset inside the sector. They only ever grow.
 *
 * The flash device is passed in, so this runs on native_sim's flash
 * simulator in tests and on the external W25Q64 in real firmware.
 */

#ifndef TANK_RECORD_FLASH_LOG_H_
#define TANK_RECORD_FLASH_LOG_H_

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include <zephyr/device.h>

#include "scan_codec.h"

/* Largest framed entry: type, 16-bit length, payload, CRC-16. */
#define TANK_FLASH_LOG_FRAME_MAX (3U + TANK_SCAN_MAX_ENCODED + 2U)

struct tank_flash_log_config {
	const struct device *flash;
	/* Partition start and size in bytes; both multiples of sector_size. */
	size_t offset;
	size_t size;
	/* Erase sector size: 4096 on the W25Q64. */
	size_t sector_size;
	/* Write a full scan at least every this many scans. */
	uint32_t full_interval;
	/* Persist the delivered position to flash every this many acks. Acks
	 * since the last persisted one are resent after a power cut; the cloud
	 * drops duplicates (P1-17).
	 */
	uint32_t ack_persist_interval;
};

/* Where a scan sat in time: what a gap record's `first` and `last` carry
 * (interfaces/records.cddl `lost-scan`).
 */
struct tank_log_mark {
	uint8_t boot_id[TANK_BOOT_ID_LEN];
	uint32_t seq;
	uint32_t up_ms;
	bool tk;
	uint64_t t_s;
};

/* Every scan from first to last was dropped; lost of them are counted here
 * (interfaces/records.cddl `gap-record`).
 */
struct tank_log_gap {
	uint32_t lost;
	struct tank_log_mark first;
	struct tank_log_mark last;
};

enum tank_log_item_kind {
	TANK_LOG_ITEM_SCAN,
	/* Scans were dropped because the log was full. */
	TANK_LOG_ITEM_GAP,
};

struct tank_log_item {
	enum tank_log_item_kind kind;
	struct tank_scan scan;
	/* For a gap item: which undelivered scans were dropped. */
	struct tank_log_gap gap;
	/* Position just after this item; pass to tank_flash_log_ack(). */
	uint64_t end_pos;
};

/* Treat the fields as private. */
struct tank_flash_log {
	struct tank_flash_log_config cfg;
	uint32_t sector_count;
	uint32_t head_seq;
	size_t head_off;
	uint64_t tail_pos;
	uint64_t ack_pos;
	uint32_t acks_unpersisted;
	uint64_t read_pos;
	struct tank_scan write_prev;
	bool write_prev_valid;
	uint32_t since_full;
	struct tank_scan read_prev;
	bool read_prev_valid;
	struct tank_scan drop_scan;
	uint32_t lost_scans;
	bool mounted;
	uint8_t frame[TANK_FLASH_LOG_FRAME_MAX];
};

/*
 * Open the log, recovering its state from flash (an erased partition gives
 * an empty log). Reading restarts at the last persisted delivered position.
 * Returns 0, -EINVAL for a bad configuration (fewer than two sectors), or a
 * flash driver error.
 */
int tank_flash_log_mount(struct tank_flash_log *log, const struct tank_flash_log_config *cfg);

/* Append one scan. Returns 0, -EINVAL, or a flash driver error. */
int tank_flash_log_append(struct tank_flash_log *log, const struct tank_scan *scan);

/* Read the next undelivered item. Returns 0, -ENODATA when there is nothing
 * more to read, -EINVAL, or a flash driver error.
 */
int tank_flash_log_read_next(struct tank_flash_log *log, struct tank_log_item *out);

/* Everything up to end_pos is delivered. Returns 0, -EINVAL, or a flash
 * driver error.
 */
int tank_flash_log_ack(struct tank_flash_log *log, uint64_t end_pos);

/* Forget what was read but not acknowledged, so it is read again. */
void tank_flash_log_rewind(struct tank_flash_log *log);

/* Undelivered scans dropped because the log was full, since mount. */
uint32_t tank_flash_log_lost_scans(const struct tank_flash_log *log);

#endif /* TANK_RECORD_FLASH_LOG_H_ */
