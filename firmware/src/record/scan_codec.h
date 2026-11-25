/*
 * Compact, lossless encoding of one scan for the flash log (S-039, P1-14).
 *
 * ADR-0004 decision 12: the outage buffer is delta encoded with regular full
 * snapshots. A full entry carries everything needed to rebuild a scan on its
 * own; a delta entry carries only what changed since the previous scan of the
 * same boot. Both are lossless: decoding gives back exactly the scan that was
 * encoded, including boot id, seq, up, tk, t, quality and age, so forwarded
 * records keep their original timestamps (ADR-0004 decision 11).
 *
 * The device id and record schema version are constant per device and are
 * added when a record is sent, not stored per scan.
 *
 * Layout (unsigned varints, signed values zigzag varints):
 *   full:  boot_id[16] sl seq up flags [t] count { id qflags [val] age }*
 *   delta: d_seq d_up flags [d_t] meta[(count+7)/8] vals[(count+7)/8]
 *          { [qflags age] [d_val] }*
 * where qflags is the quality in the low bits and bit 7 set when val is
 * present. The meta bitmap marks readings whose quality, presence or age
 * changed and the vals bitmap those whose value changed, so a noisy
 * analogue costs one byte a scan.
 */

#ifndef TANK_RECORD_SCAN_CODEC_H_
#define TANK_RECORD_SCAN_CODEC_H_

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "boot_time.h"

/* More than the 23 one-second Phase 1 signals, so a later signal list fits. */
#define TANK_SCAN_MAX_READINGS 32U

/* Upper bound of an encoded full scan, for sizing buffers. */
#define TANK_SCAN_MAX_ENCODED (TANK_BOOT_ID_LEN + 40U + TANK_SCAN_MAX_READINGS * 20U)

struct tank_scan_reading {
	uint16_t id;
	bool has_val;
	/* Scaled integer; 0 when has_val is false. */
	int32_t val;
	/* enum tank_reading_quality (interfaces/records.cddl `quality`). */
	uint8_t q;
	uint32_t age_ms;
};

struct tank_scan {
	uint8_t boot_id[TANK_BOOT_ID_LEN];
	/* signals-v?.yaml version the ids come from (`sl`). */
	uint32_t sl;
	uint32_t seq;
	uint32_t up_ms;
	bool tk;
	/* Unix seconds UTC; meaningful only when tk is true. */
	uint64_t t_s;
	uint8_t count;
	struct tank_scan_reading r[TANK_SCAN_MAX_READINGS];
};

/* Encode s on its own. Returns the length, or 0 if s is invalid or cap is
 * too small.
 */
size_t tank_scan_encode_full(const struct tank_scan *s, uint8_t *buf, size_t cap);

/* True when s can be delta encoded against prev: same boot, signal list and
 * signal ids, with seq and up not going backwards.
 */
bool tank_scan_can_delta(const struct tank_scan *prev, const struct tank_scan *s);

/* Encode s as the change since prev. Returns the length, or 0 if
 * tank_scan_can_delta() is false or cap is too small.
 */
size_t tank_scan_encode_delta(const struct tank_scan *prev, const struct tank_scan *s, uint8_t *buf,
			      size_t cap);

/* Decode a full entry. Returns 0, or -EINVAL if the bytes are malformed. */
int tank_scan_decode_full(const uint8_t *buf, size_t len, struct tank_scan *out);

/* Decode a delta entry against prev; out may be prev itself, to decode in
 * place. Returns 0, or -EINVAL if malformed.
 */
int tank_scan_decode_delta(const struct tank_scan *prev, const uint8_t *buf, size_t len,
			   struct tank_scan *out);

#endif /* TANK_RECORD_SCAN_CODEC_H_ */
