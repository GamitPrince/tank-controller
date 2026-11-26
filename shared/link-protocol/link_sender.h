/*
 * Stop-and-wait sender for RECORD frames on the FRDM-to-ESP32 UART link
 * (S-043, ADR-0004 decision 5).
 *
 * One RECORD is in flight at a time. It is complete when a DELIVERED naming
 * its seq arrives. Otherwise the same frame, with the same seq, is written
 * again every ack_timeout_ms, and after max_attempts writes the sender gives
 * up with -ETIMEDOUT. Giving up loses nothing: the record is still in the
 * flash log, and log_forwarder (S-039) rewinds and resends it later
 * (ADR-0004 decision 3).
 *
 * Time is passed in as a millisecond counter, so tests need no real waiting.
 * Elapsed time uses unsigned subtraction, so a wrapping counter is safe.
 *
 * Standard C only, like link_frame, so the ESP32 can build it.
 */

#ifndef TANK_COMMUNICATIONS_LINK_SENDER_H_
#define TANK_COMMUNICATIONS_LINK_SENDER_H_

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "link_frame.h"

/*
 * [Confirm] Defaults: 3 attempts of 3 s each is 9 s, inside ADR-0004
 * decision 8's failover after about 10 s without a cloud ack.
 */
#define TANK_LINK_ACK_TIMEOUT_MS 3000U
#define TANK_LINK_MAX_ATTEMPTS 3U

/* tank_link_sender_on_msg() result when the RECORD in flight is confirmed. */
#define TANK_LINK_SEND_CONFIRMED 1

/* Writes a whole frame to the UART. Returns 0 or a negative error. */
typedef int (*tank_link_write_fn)(void *ctx, const uint8_t *bytes, size_t len);

struct tank_link_sender_config {
	uint32_t ack_timeout_ms;
	/* Writes of one RECORD in total, the first one included. */
	uint32_t max_attempts;
};

struct tank_link_sender_stats {
	uint32_t sent;
	uint32_t retransmitted;
	uint32_t confirmed;
	uint32_t given_up;
	/* DELIVERED that names no RECORD in flight, or is malformed. */
	uint32_t stale_acks;
};

/* Treat the fields as private; read the counters through stats. */
struct tank_link_sender {
	struct tank_link_sender_config cfg;
	tank_link_write_fn write_fn;
	void *ctx;
	uint8_t frame[TANK_LINK_FRAME_MAX];
	size_t frame_len;
	bool in_flight;
	uint16_t next_seq;
	uint16_t in_flight_seq;
	uint32_t attempts;
	uint32_t last_write_ms;
	struct tank_link_sender_stats stats;
};

/* The defaults above. */
struct tank_link_sender_config tank_link_sender_default_config(void);

/*
 * Returns 0, or -EINVAL for a NULL argument, a zero timeout or zero
 * attempts. The first RECORD uses seq 0.
 */
int tank_link_sender_init(struct tank_link_sender *s, const struct tank_link_sender_config *cfg,
			  tank_link_write_fn write_fn, void *ctx);

/*
 * Encode payload as a RECORD with the next seq and write it. Returns 0,
 * -EBUSY while a RECORD is in flight (nothing is written), -EINVAL for a bad
 * argument or oversize payload, or the write_fn error. Nothing is in flight
 * after an error, and the seq is not used up.
 */
int tank_link_sender_send(struct tank_link_sender *s, const uint8_t *payload, size_t len,
			  uint32_t now_ms);

/*
 * Offer a decoded frame. Returns TANK_LINK_SEND_CONFIRMED when it is the
 * DELIVERED for the RECORD in flight, which frees the sender; otherwise 0.
 * Other message types are ignored.
 */
int tank_link_sender_on_msg(struct tank_link_sender *s, const struct tank_link_msg *msg);

/*
 * Call regularly. Once ack_timeout_ms has passed since the last write,
 * writes the frame again, or after max_attempts writes gives up and returns
 * -ETIMEDOUT, which frees the sender. Returns 0 otherwise, or the write_fn
 * error from a retransmission (the attempt still counts, so the sender
 * gives up in time even if the UART keeps failing).
 */
int tank_link_sender_poll(struct tank_link_sender *s, uint32_t now_ms);

bool tank_link_sender_busy(const struct tank_link_sender *s);

/*
 * Milliseconds until tank_link_sender_poll() next has something to do (0
 * when it is due now, or when nothing is in flight), so a caller can wait
 * for a reply without overshooting a retransmission (S-045).
 */
uint32_t tank_link_sender_wait_ms(const struct tank_link_sender *s, uint32_t now_ms);

/*
 * Drop the RECORD in flight without confirming it, when the caller can no
 * longer receive its DELIVERED (a UART read error, S-045). A DELIVERED that
 * arrives for it later counts as stale. Counted as given up.
 */
void tank_link_sender_abandon(struct tank_link_sender *s);

const struct tank_link_sender_stats *tank_link_sender_stats(const struct tank_link_sender *s);

#endif /* TANK_COMMUNICATIONS_LINK_SENDER_H_ */
