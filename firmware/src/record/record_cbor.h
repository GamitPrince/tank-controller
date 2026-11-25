/*
 * Encode flash log items as the CBOR records of interfaces/records.cddl
 * version 1 (S-044, P1-12; ADR-0004 decision 6).
 *
 * A scan item becomes a `record` and a gap item a `gap-record`, each ready to
 * be the payload of one RECORD frame on the UART link. The encoding is
 * deterministic (RFC 8949 section 4.2.1): definite lengths, shortest-form
 * integers and map keys in core deterministic order, so the same item always
 * gives the same bytes.
 *
 * Input the schema would reject is refused rather than sent: no readings, a
 * quality code it does not define, a value on a fault or unconfigured
 * reading, a bad device id, or a gap that counts no lost scans.
 *
 * [Confirm] Digital values are sent as the integers 0 and 1, not as CBOR
 * booleans: a reading holds an int32_t and does not know its signal's unit,
 * and the schema accepts `int / bool`.
 *
 * No CBOR library and no Zephyr API calls; the item types come from
 * flash_log.h.
 */

#ifndef TANK_RECORD_RECORD_CBOR_H_
#define TANK_RECORD_RECORD_CBOR_H_

#include <stddef.h>
#include <stdint.h>

#include "flash_log.h"
#include "scan_codec.h"

/* The `v` every version 1 record carries. */
#define TANK_RECORD_SCHEMA_VERSION 1U

/*
 * [Confirm] The schema allows 64 bytes; the firmware limits itself to 32 so a
 * worst-case scan fits in one RECORD frame. Revisit when ADR-0005 fixes the
 * device id format.
 */
#define TANK_RECORD_DEV_ID_MAX 32U

/*
 * Worst-case encoded scan, every integer at its widest. A reading is a map
 * header (1), "q" and its code (2 + 1), "id" and a uint16 (3 + 3), "age" and
 * a uint32 (4 + 5), "val" and an int32 (4 + 5). The record around the
 * readings is a map header (1), "r" and the array header (2 + 2), "t" and a
 * uint64 (2 + 9), "v" (2 + 1), "sl" (3 + 5), "tk" (3 + 1), "up" (3 + 5),
 * "dev" and a text header and the id (4 + 2 + 32), "seq" (4 + 5), "boot"
 * and a 16-byte string (5 + 1 + 16). A gap record is smaller.
 */
#define TANK_RECORD_CBOR_READING_MAX 28U
#define TANK_RECORD_CBOR_HEAD_MAX (76U + TANK_RECORD_DEV_ID_MAX)
#define TANK_RECORD_CBOR_MAX                                                                       \
	(TANK_RECORD_CBOR_HEAD_MAX + TANK_SCAN_MAX_READINGS * TANK_RECORD_CBOR_READING_MAX)

/*
 * dev_id is the NUL-terminated device id (1 to TANK_RECORD_DEV_ID_MAX
 * bytes). Each function returns the encoded length, or 0 if the input is
 * invalid or cap is too small.
 */
size_t tank_record_cbor_encode_scan(const char *dev_id, const struct tank_scan *scan, uint8_t *buf,
				    size_t cap);

size_t tank_record_cbor_encode_gap(const char *dev_id, const struct tank_log_gap *gap, uint8_t *buf,
				   size_t cap);

/* Encode a scan or gap item by its kind. */
size_t tank_record_cbor_encode_item(const char *dev_id, const struct tank_log_item *item,
				    uint8_t *buf, size_t cap);

#endif /* TANK_RECORD_RECORD_CBOR_H_ */
