/*
 * Send the flash log to the ESP32 over the UART link (S-045, P1-12).
 *
 * tank_uplink_send() is log_forwarder's send_fn (S-039). Each item is
 * encoded as a CBOR record (S-044), sent as one RECORD and waited on until
 * the ESP32 confirms it (S-043), which means the cloud has it. Items go one
 * at a time, in order; the first that fails ends the batch, and the count
 * confirmed before it is returned, so log_forwarder acks those and resends
 * only the rest (ADR-0004 decisions 3 and 5).
 *
 * An item that cannot be encoded returns -EINVAL and is counted. It stays in
 * the flash log and blocks the items behind it; what to do with an item
 * that can never be sent is a later story.
 *
 * Phase 1: records go out and only DELIVERED is read back. Nothing here
 * carries a command to the plant or to the FRDM's measurement.
 *
 * Standard C only, like the link modules. The UART glue that implements
 * read_fn and write_fn is a later story.
 */

#ifndef TANK_COMMUNICATIONS_UPLINK_H_
#define TANK_COMMUNICATIONS_UPLINK_H_

#include <stddef.h>
#include <stdint.h>

#include "flash_log.h"
#include "link_frame.h"
#include "link_sender.h"
#include "record_cbor.h"

/*
 * Wait up to timeout_ms for one decoded link frame. Returns 0 with *msg
 * filled (its payload valid until the next call), -EAGAIN on timeout, or
 * another negative error.
 */
typedef int (*tank_uplink_read_fn)(void *ctx, struct tank_link_msg *msg, uint32_t timeout_ms);

/* Milliseconds, the clock link_sender uses. */
typedef uint32_t (*tank_uplink_now_fn)(void *ctx);

struct tank_uplink_io {
	tank_link_write_fn write_fn;
	tank_uplink_read_fn read_fn;
	tank_uplink_now_fn now_fn;
	void *ctx;
};

struct tank_uplink_stats {
	uint32_t sent;
	uint32_t confirmed;
	uint32_t link_give_ups;
	uint32_t encode_failures;
};

/* Treat the fields as private; read the counters through stats. */
struct tank_uplink {
	const char *dev_id;
	struct tank_uplink_io io;
	struct tank_link_sender sender;
	uint8_t record[TANK_RECORD_CBOR_MAX];
	struct tank_uplink_stats stats;
};

/*
 * dev_id must stay valid while the uplink is used. Returns 0, or -EINVAL for
 * a NULL argument or a bad link configuration.
 */
int tank_uplink_init(struct tank_uplink *up, const char *dev_id,
		     const struct tank_link_sender_config *link_cfg,
		     const struct tank_uplink_io *io);

/*
 * A tank_log_send_fn; ctx is the struct tank_uplink. Returns how many
 * leading items the ESP32 confirmed (1 to count), or, when it confirmed
 * none: -ETIMEDOUT when the link gave up, -EINVAL for an item that cannot be
 * encoded or a bad argument, or the read_fn or write_fn error.
 */
int tank_uplink_send(void *ctx, const struct tank_log_item *items, size_t count);

const struct tank_uplink_stats *tank_uplink_stats(const struct tank_uplink *up);

#endif /* TANK_COMMUNICATIONS_UPLINK_H_ */
