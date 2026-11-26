/*
 * Stop-and-wait sender on the FRDM-to-ESP32 UART link (S-043). See
 * link_sender.h. Standard C only, so the ESP32 can build the same file.
 */

#include "link_sender.h"

#include <errno.h>
#include <string.h>

#define BITS_PER_BYTE 8U

struct tank_link_sender_config tank_link_sender_default_config(void)
{
	const struct tank_link_sender_config cfg = {
	    .ack_timeout_ms = TANK_LINK_ACK_TIMEOUT_MS,
	    .max_attempts = TANK_LINK_MAX_ATTEMPTS,
	};

	return cfg;
}

int tank_link_sender_init(struct tank_link_sender *s, const struct tank_link_sender_config *cfg,
			  tank_link_write_fn write_fn, void *ctx)
{
	if (s == NULL || cfg == NULL || write_fn == NULL || cfg->ack_timeout_ms == 0U ||
	    cfg->max_attempts == 0U) {
		return -EINVAL;
	}
	memset(s, 0, sizeof(*s));
	s->cfg = *cfg;
	s->write_fn = write_fn;
	s->ctx = ctx;
	return 0;
}

int tank_link_sender_send(struct tank_link_sender *s, const uint8_t *payload, size_t len,
			  uint32_t now_ms)
{
	struct tank_link_msg msg;
	int err;

	if (s == NULL) {
		return -EINVAL;
	}
	if (s->in_flight) {
		return -EBUSY;
	}
	msg.type = TANK_LINK_RECORD;
	msg.seq = s->next_seq;
	msg.payload = payload;
	msg.payload_len = len;
	err = tank_link_frame_encode(&msg, s->frame, sizeof(s->frame), &s->frame_len);
	if (err != 0) {
		return err;
	}
	err = s->write_fn(s->ctx, s->frame, s->frame_len);
	if (err != 0) {
		return err;
	}
	s->in_flight = true;
	s->in_flight_seq = s->next_seq;
	s->next_seq++;
	s->attempts = 1U;
	s->last_write_ms = now_ms;
	s->stats.sent++;
	return 0;
}

static uint16_t delivered_seq(const struct tank_link_msg *msg)
{
	return (uint16_t)(msg->payload[0] | ((uint16_t)msg->payload[1] << BITS_PER_BYTE));
}

int tank_link_sender_on_msg(struct tank_link_sender *s, const struct tank_link_msg *msg)
{
	if (s == NULL || msg == NULL || msg->type != TANK_LINK_DELIVERED) {
		return 0;
	}
	if (!s->in_flight || msg->payload == NULL ||
	    msg->payload_len != TANK_LINK_DELIVERED_PAYLOAD_LEN ||
	    delivered_seq(msg) != s->in_flight_seq) {
		s->stats.stale_acks++;
		return 0;
	}
	s->in_flight = false;
	s->stats.confirmed++;
	return TANK_LINK_SEND_CONFIRMED;
}

int tank_link_sender_poll(struct tank_link_sender *s, uint32_t now_ms)
{
	if (s == NULL || !s->in_flight) {
		return 0;
	}
	if ((uint32_t)(now_ms - s->last_write_ms) < s->cfg.ack_timeout_ms) {
		return 0;
	}
	if (s->attempts >= s->cfg.max_attempts) {
		s->in_flight = false;
		s->stats.given_up++;
		return -ETIMEDOUT;
	}
	s->attempts++;
	s->last_write_ms = now_ms;
	s->stats.retransmitted++;
	return s->write_fn(s->ctx, s->frame, s->frame_len);
}

bool tank_link_sender_busy(const struct tank_link_sender *s)
{
	return s != NULL && s->in_flight;
}

uint32_t tank_link_sender_wait_ms(const struct tank_link_sender *s, uint32_t now_ms)
{
	uint32_t elapsed;

	if (s == NULL || !s->in_flight) {
		return 0U;
	}
	elapsed = now_ms - s->last_write_ms;
	return (elapsed >= s->cfg.ack_timeout_ms) ? 0U : s->cfg.ack_timeout_ms - elapsed;
}

void tank_link_sender_abandon(struct tank_link_sender *s)
{
	if (s == NULL || !s->in_flight) {
		return;
	}
	s->in_flight = false;
	s->stats.given_up++;
}

const struct tank_link_sender_stats *tank_link_sender_stats(const struct tank_link_sender *s)
{
	return (s == NULL) ? NULL : &s->stats;
}
