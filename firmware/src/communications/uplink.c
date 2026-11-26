/*
 * Send the flash log to the ESP32 over the UART link (S-045). See uplink.h.
 */

#include "uplink.h"

#include <errno.h>

/* A full batch that could outgrow one RECORD frame must not build. */
_Static_assert(TANK_UPLINK_FRAME_PAYLOAD_MAX <= TANK_LINK_PAYLOAD_MAX,
	       "a batch of records must fit in one RECORD frame");

/* CBOR major type 4 (array) with the count in the initial byte. */
#define CBOR_ARRAY_HEAD 0x80U

int tank_uplink_init(struct tank_uplink *up, const char *dev_id,
		     const struct tank_link_sender_config *link_cfg,
		     const struct tank_uplink_io *io)
{
	if (up == NULL || dev_id == NULL || io == NULL || io->read_fn == NULL ||
	    io->now_fn == NULL) {
		return -EINVAL;
	}
	up->dev_id = dev_id;
	up->io = *io;
	up->stats = (struct tank_uplink_stats){0};
	return tank_link_sender_init(&up->sender, link_cfg, io->write_fn, io->ctx);
}

/* Read and poll until the RECORD in flight is confirmed or the link fails. */
static int await_confirmation(struct tank_uplink *up)
{
	struct tank_link_msg msg;
	uint32_t wait;
	int rc;

	for (;;) {
		wait = tank_link_sender_wait_ms(&up->sender, up->io.now_fn(up->io.ctx));
		rc = up->io.read_fn(up->io.ctx, &msg, wait);
		if (rc == 0 &&
		    tank_link_sender_on_msg(&up->sender, &msg) == TANK_LINK_SEND_CONFIRMED) {
			up->stats.confirmed++;
			return 0;
		}
		if (rc != 0 && rc != -EAGAIN) {
			tank_link_sender_abandon(&up->sender);
			return rc;
		}
		/* A failed retransmission still counts as an attempt, so keep going. */
		rc = tank_link_sender_poll(&up->sender, up->io.now_fn(up->io.ctx));
		if (rc == -ETIMEDOUT) {
			up->stats.link_give_ups++;
			return rc;
		}
	}
}

/*
 * Pack up to max leading items into up->frame as a batch. Returns how many
 * were packed (0 when the first cannot be encoded) and sets *len.
 */
static size_t pack_frame(struct tank_uplink *up, const struct tank_log_item *items, size_t max,
			 size_t *len)
{
	size_t used = 1U;
	size_t n = 0U;

	while (n < max) {
		size_t rec = tank_record_cbor_encode_item(up->dev_id, &items[n], &up->frame[used],
							  sizeof(up->frame) - used);

		if (rec == 0U) {
			up->stats.encode_failures++;
			break;
		}
		used += rec;
		n++;
	}
	up->frame[0] = (uint8_t)(CBOR_ARRAY_HEAD | n);
	*len = used;
	return n;
}

/* Send one frame of up to max items. Returns how many it carried, or < 0. */
static int send_frame(struct tank_uplink *up, const struct tank_log_item *items, size_t max)
{
	size_t len;
	size_t n = pack_frame(up, items, max, &len);
	int rc;

	if (n == 0U) {
		return -EINVAL;
	}
	rc = tank_link_sender_send(&up->sender, up->frame, len, up->io.now_fn(up->io.ctx));
	if (rc != 0) {
		return rc;
	}
	up->stats.sent++;
	rc = await_confirmation(up);
	return (rc != 0) ? rc : (int)n;
}

int tank_uplink_send(void *ctx, const struct tank_log_item *items, size_t count)
{
	struct tank_uplink *up = ctx;
	size_t done = 0U;
	int rc = 0;

	if (up == NULL || items == NULL || count == 0U) {
		return -EINVAL;
	}
	while (done < count) {
		const size_t left = count - done;

		rc = send_frame(up, &items[done],
				(left < TANK_UPLINK_BATCH_MAX) ? left : TANK_UPLINK_BATCH_MAX);
		if (rc <= 0) {
			break;
		}
		done += (size_t)rc;
		if ((size_t)rc < TANK_UPLINK_BATCH_MAX && done < count) {
			/* An item that cannot be encoded ended this frame early. */
			break;
		}
	}
	return (done > 0U) ? (int)done : rc;
}

const struct tank_uplink_stats *tank_uplink_stats(const struct tank_uplink *up)
{
	return (up == NULL) ? NULL : &up->stats;
}
