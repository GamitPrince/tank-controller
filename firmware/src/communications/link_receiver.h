/*
 * Duplicate detection for RECORD frames on the FRDM-to-ESP32 UART link
 * (S-043, ADR-0004 decision 5). This is the ESP32 side, built and tested on
 * native_sim like the rest of the shared link library.
 *
 * The FRDM resends a RECORD, with the same seq and bytes, when its
 * DELIVERED is lost or late (link_sender.h). The receiver passes each
 * RECORD up once. A repeat of the RECORD already confirmed gets its
 * DELIVERED again, so a lost DELIVERED does not stall the sender; a repeat
 * of one not yet confirmed is dropped without a reply.
 *
 * Duplicate rule: the same seq AND the same payload length and CRC-16 as
 * the last RECORD accepted. Checking the payload as well as the seq means a
 * FRDM that reboots and restarts its seq is not mistaken for a resend.
 * [Confirm] Residual risk: a new RECORD with the same seq, length and
 * CRC-16 as the previous one (about 1 in 65536 after a seq restart). The
 * cloud also deduplicates on boot id and seq (ADR-0004 decision 11).
 *
 * Standard C only, like link_frame.
 */

#ifndef TANK_COMMUNICATIONS_LINK_RECEIVER_H_
#define TANK_COMMUNICATIONS_LINK_RECEIVER_H_

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "link_frame.h"

/* What the caller does with a frame offered to the receiver. */
enum tank_link_recv_action {
	/* Not a RECORD, or a repeat still awaiting the upper layer: nothing. */
	TANK_LINK_RECV_NONE = 0,
	/* A new RECORD: pass it up, then confirm it once the cloud has it. */
	TANK_LINK_RECV_DELIVER = 1,
	/* A repeat of the RECORD already confirmed: confirm it again. */
	TANK_LINK_RECV_RECONFIRM = 2,
};

struct tank_link_receiver_stats {
	uint32_t accepted;
	uint32_t duplicates;
};

/* Treat the fields as private; read the counters through stats. */
struct tank_link_receiver {
	bool have_last;
	bool last_confirmed;
	uint16_t last_seq;
	size_t last_len;
	uint16_t last_crc;
	/* Header seq of the DELIVERED frames this side sends. */
	uint16_t tx_seq;
	struct tank_link_receiver_stats stats;
};

void tank_link_receiver_init(struct tank_link_receiver *r);

/*
 * Offer a decoded frame. Returns a tank_link_recv_action, or -EINVAL for a
 * NULL argument or a RECORD with a NULL payload of non-zero length.
 */
int tank_link_receiver_on_msg(struct tank_link_receiver *r, const struct tank_link_msg *msg);

/*
 * Build the DELIVERED frame for seq, which must be the last RECORD
 * accepted, into out. Returns 0 and sets *out_len, -EINVAL for a bad
 * argument or any other seq, or -ENOSPC if out_cap is too small.
 */
int tank_link_receiver_confirm(struct tank_link_receiver *r, uint16_t seq, uint8_t *out,
			       size_t out_cap, size_t *out_len);

const struct tank_link_receiver_stats *tank_link_receiver_stats(const struct tank_link_receiver *r);

#endif /* TANK_COMMUNICATIONS_LINK_RECEIVER_H_ */
