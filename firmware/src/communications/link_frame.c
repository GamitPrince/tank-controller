/*
 * Frames on the FRDM-to-ESP32 UART link (S-042). See link_frame.h.
 * Standard C only, so the ESP32 can build the same file.
 */

#include "link_frame.h"

#include <errno.h>

#define DELIMITER 0x00U
#define COBS_BLOCK_END 0xFFU
#define CRC_INIT 0xFFFFU
#define CRC_POLY 0x1021U
#define CRC_TOP_BIT 0x8000U
#define BITS_PER_BYTE 8U
#define BYTE_MASK 0xFFU

/* COBS encoder that writes straight into the caller's buffer. */
struct cobs_writer {
	uint8_t *out;
	size_t cap;
	size_t len;
	size_t code_idx;
	uint8_t code;
	bool overflow;
};

static uint16_t crc16_update(uint16_t crc, const uint8_t *data, size_t len)
{
	for (size_t i = 0; i < len; i++) {
		crc ^= (uint16_t)((uint16_t)data[i] << BITS_PER_BYTE);
		for (unsigned int bit = 0; bit < BITS_PER_BYTE; bit++) {
			crc = (crc & CRC_TOP_BIT) ? (uint16_t)((crc << 1) ^ CRC_POLY)
						  : (uint16_t)(crc << 1);
		}
	}
	return crc;
}

uint16_t tank_link_crc16(const uint8_t *data, size_t len)
{
	return crc16_update(CRC_INIT, data, len);
}

static void cobs_emit(struct cobs_writer *w, uint8_t b)
{
	if (w->len >= w->cap) {
		w->overflow = true;
		return;
	}
	w->out[w->len++] = b;
}

/* Fill in the current block's code byte and reserve the next one. */
static void cobs_close_block(struct cobs_writer *w)
{
	if (w->code_idx < w->cap) {
		w->out[w->code_idx] = w->code;
	}
	w->code_idx = w->len;
	w->code = 1U;
	cobs_emit(w, 0U);
}

static void cobs_start(struct cobs_writer *w, uint8_t *out, size_t cap)
{
	w->out = out;
	w->cap = cap;
	w->len = 0U;
	w->code_idx = 0U;
	w->code = 1U;
	w->overflow = false;
	cobs_emit(w, 0U);
}

static void cobs_put(struct cobs_writer *w, uint8_t b)
{
	if (b == DELIMITER) {
		cobs_close_block(w);
		return;
	}
	cobs_emit(w, b);
	w->code++;
	if (w->code == COBS_BLOCK_END) {
		cobs_close_block(w);
	}
}

static void cobs_put_all(struct cobs_writer *w, const uint8_t *data, size_t len)
{
	for (size_t i = 0; i < len; i++) {
		cobs_put(w, data[i]);
	}
}

static void cobs_finish(struct cobs_writer *w)
{
	if (w->code_idx < w->cap) {
		w->out[w->code_idx] = w->code;
	}
	cobs_emit(w, DELIMITER);
}

static bool type_valid(uint8_t type)
{
	return type >= TANK_LINK_RECORD && type <= TANK_LINK_TIME;
}

static bool msg_valid(const struct tank_link_msg *msg)
{
	return msg != NULL && type_valid(msg->type) && msg->payload_len <= TANK_LINK_PAYLOAD_MAX &&
	       (msg->payload != NULL || msg->payload_len == 0U);
}

/* CRC over header then payload, without joining them in a buffer. */
static uint16_t body_crc(const uint8_t *header, const struct tank_link_msg *msg)
{
	const uint16_t crc = crc16_update(CRC_INIT, header, TANK_LINK_HEADER_LEN);

	return crc16_update(crc, msg->payload, msg->payload_len);
}

int tank_link_frame_encode(const struct tank_link_msg *msg, uint8_t *out, size_t out_cap,
			   size_t *out_len)
{
	if (!msg_valid(msg) || out == NULL || out_len == NULL) {
		return -EINVAL;
	}

	const uint8_t header[TANK_LINK_HEADER_LEN] = {
	    TANK_LINK_VERSION,
	    msg->type,
	    (uint8_t)(msg->seq & BYTE_MASK),
	    (uint8_t)(msg->seq >> BITS_PER_BYTE),
	};
	const uint16_t crc = body_crc(header, msg);
	const uint8_t trailer[TANK_LINK_CRC_LEN] = {
	    (uint8_t)(crc & BYTE_MASK),
	    (uint8_t)(crc >> BITS_PER_BYTE),
	};
	struct cobs_writer w;

	cobs_start(&w, out, out_cap);
	cobs_put_all(&w, header, sizeof(header));
	cobs_put_all(&w, msg->payload, msg->payload_len);
	cobs_put_all(&w, trailer, sizeof(trailer));
	cobs_finish(&w);
	if (w.overflow) {
		return -ENOSPC;
	}
	*out_len = w.len;
	return 0;
}

void tank_link_decoder_init(struct tank_link_decoder *dec)
{
	dec->raw_len = 0U;
	dec->overrun = false;
	dec->accepted = 0U;
	dec->rejected = 0U;
}

/* Returns 0, -EBADMSG for a code byte that runs past the end, or -ENOSPC. */
static int cobs_decode(const uint8_t *in, size_t len, uint8_t *out, size_t cap, size_t *out_len)
{
	size_t i = 0U;
	size_t o = 0U;

	while (i < len) {
		const uint8_t code = in[i++];

		if (code == DELIMITER || i + code - 1U > len) {
			return -EBADMSG;
		}
		for (uint8_t k = 1U; k < code; k++) {
			if (o >= cap) {
				return -ENOSPC;
			}
			out[o++] = in[i++];
		}
		if (code != COBS_BLOCK_END && i < len) {
			if (o >= cap) {
				return -ENOSPC;
			}
			out[o++] = DELIMITER;
		}
	}
	*out_len = o;
	return 0;
}

static enum tank_link_rx parse_body(const uint8_t *body, size_t len, struct tank_link_msg *msg)
{
	if (len < TANK_LINK_HEADER_LEN + TANK_LINK_CRC_LEN) {
		return TANK_LINK_RX_TOO_SHORT;
	}
	const size_t crc_at = len - TANK_LINK_CRC_LEN;
	const uint16_t crc =
	    (uint16_t)(body[crc_at] | ((uint16_t)body[crc_at + 1U] << BITS_PER_BYTE));

	if (tank_link_crc16(body, crc_at) != crc) {
		return TANK_LINK_RX_BAD_CRC;
	}
	if (body[0] != TANK_LINK_VERSION) {
		return TANK_LINK_RX_BAD_VERSION;
	}
	if (!type_valid(body[1])) {
		return TANK_LINK_RX_BAD_TYPE;
	}
	msg->type = body[1];
	msg->seq = (uint16_t)(body[2] | ((uint16_t)body[3] << BITS_PER_BYTE));
	msg->payload = &body[TANK_LINK_HEADER_LEN];
	msg->payload_len = crc_at - TANK_LINK_HEADER_LEN;
	return TANK_LINK_RX_FRAME;
}

static enum tank_link_rx finish_frame(struct tank_link_decoder *dec, struct tank_link_msg *msg)
{
	size_t body_len;
	int err;

	if (dec->overrun) {
		return TANK_LINK_RX_TOO_LONG;
	}
	if (dec->raw_len == 0U) {
		return TANK_LINK_RX_NEED_MORE;
	}
	err = cobs_decode(dec->raw, dec->raw_len, dec->body, sizeof(dec->body), &body_len);
	if (err == -ENOSPC) {
		return TANK_LINK_RX_TOO_LONG;
	}
	if (err != 0) {
		return TANK_LINK_RX_BAD_COBS;
	}
	return parse_body(dec->body, body_len, msg);
}

enum tank_link_rx tank_link_decoder_push(struct tank_link_decoder *dec, uint8_t byte,
					 struct tank_link_msg *msg)
{
	enum tank_link_rx result;

	if (byte != DELIMITER) {
		if (dec->raw_len < sizeof(dec->raw)) {
			dec->raw[dec->raw_len++] = byte;
		} else {
			dec->overrun = true;
		}
		return TANK_LINK_RX_NEED_MORE;
	}

	result = finish_frame(dec, msg);
	dec->raw_len = 0U;
	dec->overrun = false;
	if (result == TANK_LINK_RX_FRAME) {
		dec->accepted++;
	} else if (result != TANK_LINK_RX_NEED_MORE) {
		dec->rejected++;
	}
	return result;
}
