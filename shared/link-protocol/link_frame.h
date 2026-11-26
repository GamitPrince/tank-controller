/*
 * Frames on the FRDM-to-ESP32 UART link (S-042, ADR-0004 decisions 4, 5).
 *
 * On the wire a frame is COBS(body) followed by one 0x00 delimiter, so a
 * receiver that starts mid-stream or loses bytes resynchronises at the next
 * delimiter. The body, multi-byte fields little-endian:
 *
 *   version (1) | type (1) | seq (2) | payload (0..TANK_LINK_PAYLOAD_MAX)
 *   | crc (2)
 *
 * crc is CRC-16/CCITT-FALSE over version through payload.
 *
 * This file and link_frame.c use only the C standard library so the same
 * code can build for the ESP32 under ESP-IDF ("one small C library shared
 * by both boards"). Both boards build it from shared/link-protocol/ (S-056).
 *
 * Phase 1: no message type carries a command to the plant or to the FRDM's
 * measurement, and none may be added.
 */

#ifndef TANK_COMMUNICATIONS_LINK_FRAME_H_
#define TANK_COMMUNICATIONS_LINK_FRAME_H_

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define TANK_LINK_VERSION 1U
/* [Confirm] Enough for a catch-up batch of delta-encoded scans. */
#define TANK_LINK_PAYLOAD_MAX 1024U
#define TANK_LINK_HEADER_LEN 4U
#define TANK_LINK_CRC_LEN 2U
#define TANK_LINK_BODY_MAX (TANK_LINK_HEADER_LEN + TANK_LINK_PAYLOAD_MAX + TANK_LINK_CRC_LEN)
/* COBS adds one code byte per 254 data bytes plus one; then the delimiter. */
#define TANK_LINK_FRAME_MAX (TANK_LINK_BODY_MAX + TANK_LINK_BODY_MAX / 254U + 2U)
/* DELIVERED carries the confirmed seq as its payload. */
#define TANK_LINK_DELIVERED_PAYLOAD_LEN 2U

enum tank_link_type {
	/* FRDM to ESP32: a CBOR record or batch (ADR-0004 decision 6). */
	TANK_LINK_RECORD = 0x01,
	/* ESP32 to FRDM: the seq the cloud has acknowledged. */
	TANK_LINK_DELIVERED = 0x02,
	/* ESP32 to FRDM: Wi-Fi and 4G state; layout is a later slice. */
	TANK_LINK_LINK_STATUS = 0x03,
	/* ESP32 to FRDM: time; layout is a later slice. */
	TANK_LINK_TIME = 0x04,
};

struct tank_link_msg {
	uint8_t type;
	uint16_t seq;
	const uint8_t *payload;
	size_t payload_len;
};

/* Result of pushing one received byte. Rejections are negative. */
enum tank_link_rx {
	TANK_LINK_RX_NEED_MORE = 0,
	TANK_LINK_RX_FRAME = 1,
	TANK_LINK_RX_BAD_COBS = -1,
	TANK_LINK_RX_BAD_CRC = -2,
	TANK_LINK_RX_TOO_SHORT = -3,
	TANK_LINK_RX_TOO_LONG = -4,
	TANK_LINK_RX_BAD_VERSION = -5,
	TANK_LINK_RX_BAD_TYPE = -6,
};

struct tank_link_decoder {
	/* Encoded bytes received since the last delimiter. */
	uint8_t raw[TANK_LINK_FRAME_MAX];
	size_t raw_len;
	/* More bytes arrived than a frame can hold; drop until the delimiter. */
	bool overrun;
	uint8_t body[TANK_LINK_BODY_MAX];
	uint32_t accepted;
	uint32_t rejected;
};

/* CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection, no xorout. */
uint16_t tank_link_crc16(const uint8_t *data, size_t len);

/*
 * Encode msg into out, delimiter included. Returns 0 and sets *out_len,
 * -EINVAL for a bad argument, unknown type or oversize payload, or -ENOSPC
 * if out_cap is too small (out is never written past out_cap).
 */
int tank_link_frame_encode(const struct tank_link_msg *msg, uint8_t *out, size_t out_cap,
			   size_t *out_len);

void tank_link_decoder_init(struct tank_link_decoder *dec);

/*
 * Feed one received byte. On TANK_LINK_RX_FRAME, *msg is filled and its
 * payload points into dec, valid until the next byte is pushed. A lone
 * delimiter (empty frame) is ignored and returns NEED_MORE.
 */
enum tank_link_rx tank_link_decoder_push(struct tank_link_decoder *dec, uint8_t byte,
					 struct tank_link_msg *msg);

#endif /* TANK_COMMUNICATIONS_LINK_FRAME_H_ */
