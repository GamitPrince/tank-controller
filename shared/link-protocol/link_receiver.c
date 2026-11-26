/*
 * Duplicate detection on the FRDM-to-ESP32 UART link (S-043). See
 * link_receiver.h. Standard C only, so the ESP32 can build the same file.
 */

#include "link_receiver.h"

#include <errno.h>
#include <string.h>

#define BITS_PER_BYTE 8U
#define BYTE_MASK 0xFFU

void tank_link_receiver_init(struct tank_link_receiver *r)
{
	if (r != NULL) {
		memset(r, 0, sizeof(*r));
	}
}

static bool is_repeat(const struct tank_link_receiver *r, const struct tank_link_msg *msg,
		      uint16_t crc)
{
	return r->have_last && msg->seq == r->last_seq && msg->payload_len == r->last_len &&
	       crc == r->last_crc;
}

int tank_link_receiver_on_msg(struct tank_link_receiver *r, const struct tank_link_msg *msg)
{
	uint16_t crc;

	if (r == NULL || msg == NULL) {
		return -EINVAL;
	}
	if (msg->type != TANK_LINK_RECORD) {
		return TANK_LINK_RECV_NONE;
	}
	if (msg->payload == NULL && msg->payload_len != 0U) {
		return -EINVAL;
	}
	crc = tank_link_crc16(msg->payload, msg->payload_len);
	if (is_repeat(r, msg, crc)) {
		r->stats.duplicates++;
		return r->last_confirmed ? TANK_LINK_RECV_RECONFIRM : TANK_LINK_RECV_NONE;
	}
	r->have_last = true;
	r->last_confirmed = false;
	r->last_seq = msg->seq;
	r->last_len = msg->payload_len;
	r->last_crc = crc;
	r->stats.accepted++;
	return TANK_LINK_RECV_DELIVER;
}

int tank_link_receiver_confirm(struct tank_link_receiver *r, uint16_t seq, uint8_t *out,
			       size_t out_cap, size_t *out_len)
{
	const uint8_t payload[TANK_LINK_DELIVERED_PAYLOAD_LEN] = {
	    (uint8_t)(seq & BYTE_MASK),
	    (uint8_t)(seq >> BITS_PER_BYTE),
	};
	const struct tank_link_msg msg = {
	    .type = TANK_LINK_DELIVERED,
	    .seq = (r == NULL) ? 0U : r->tx_seq,
	    .payload = payload,
	    .payload_len = sizeof(payload),
	};
	int err;

	if (r == NULL || !r->have_last || seq != r->last_seq) {
		return -EINVAL;
	}
	err = tank_link_frame_encode(&msg, out, out_cap, out_len);
	if (err != 0) {
		return err;
	}
	r->tx_seq++;
	r->last_confirmed = true;
	return 0;
}

const struct tank_link_receiver_stats *tank_link_receiver_stats(const struct tank_link_receiver *r)
{
	return (r == NULL) ? NULL : &r->stats;
}
