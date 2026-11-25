/*
 * The ESP32 end of the FRDM-to-ESP32 UART link (S-047). See link_endpoint.h.
 */

#include "link_endpoint.h"

#include <errno.h>
#include <string.h>

/* A DELIVERED frame: header, seq payload and CRC, COBS overhead, delimiter. */
#define DELIVERED_BODY_LEN                                                                         \
	(TANK_LINK_HEADER_LEN + TANK_LINK_DELIVERED_PAYLOAD_LEN + TANK_LINK_CRC_LEN)
#define DELIVERED_FRAME_MAX (DELIVERED_BODY_LEN + DELIVERED_BODY_LEN / 254U + 2U)

int tank_link_endpoint_init(struct tank_link_endpoint *ep, tank_link_record_fn record_fn,
			    tank_link_endpoint_write_fn write_fn, void *ctx)
{
	if (ep == NULL || record_fn == NULL || write_fn == NULL) {
		return -EINVAL;
	}
	memset(ep, 0, sizeof(*ep));
	tank_link_decoder_init(&ep->dec);
	tank_link_receiver_init(&ep->rx);
	ep->record_fn = record_fn;
	ep->write_fn = write_fn;
	ep->ctx = ctx;
	return 0;
}

int tank_link_endpoint_confirm(struct tank_link_endpoint *ep, uint16_t seq)
{
	uint8_t frame[DELIVERED_FRAME_MAX];
	size_t len;
	int err;

	if (ep == NULL) {
		return -EINVAL;
	}
	err = tank_link_receiver_confirm(&ep->rx, seq, frame, sizeof(frame), &len);
	if (err != 0) {
		return err;
	}
	err = ep->write_fn(ep->ctx, frame, len);
	if (err == 0) {
		ep->stats.confirms_written++;
	}
	return err;
}

static int on_frame(struct tank_link_endpoint *ep, const struct tank_link_msg *msg)
{
	int action;

	ep->stats.frames++;
	if (msg->type != TANK_LINK_RECORD) {
		ep->stats.ignored++;
		return 0;
	}
	action = tank_link_receiver_on_msg(&ep->rx, msg);
	if (action == TANK_LINK_RECV_DELIVER) {
		ep->stats.records++;
		ep->record_fn(ep->ctx, msg->seq, msg->payload, msg->payload_len);
		return 0;
	}
	ep->stats.duplicates++;
	return (action == TANK_LINK_RECV_RECONFIRM) ? tank_link_endpoint_confirm(ep, msg->seq) : 0;
}

int tank_link_endpoint_push(struct tank_link_endpoint *ep, uint8_t byte)
{
	struct tank_link_msg msg;
	enum tank_link_rx rx;

	if (ep == NULL) {
		return -EINVAL;
	}
	rx = tank_link_decoder_push(&ep->dec, byte, &msg);
	if (rx == TANK_LINK_RX_FRAME) {
		return on_frame(ep, &msg);
	}
	if (rx < 0 && (size_t)(-rx) <= TANK_LINK_ENDPOINT_REJECT_REASONS) {
		ep->stats.rejected[-rx - 1]++;
	}
	return 0;
}

const struct tank_link_endpoint_stats *tank_link_endpoint_stats(const struct tank_link_endpoint *ep)
{
	return (ep == NULL) ? NULL : &ep->stats;
}
