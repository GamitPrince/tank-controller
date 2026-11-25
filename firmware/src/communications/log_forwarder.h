/*
 * Forward the flash log to the cloud, oldest first (S-039, P1-14).
 *
 * Each poll reads up to one batch of undelivered items from the flash log
 * (firmware/src/record/flash_log.h) and hands them to send_fn. When send_fn
 * reports a cloud acknowledgement the batch is marked delivered; otherwise
 * it is rewound and resent on a later poll, so nothing is lost while the
 * link is down. Items keep the boot id, seq, up, tk and t they were logged
 * with (ADR-0004 decision 11); records are batched when catching up
 * (ADR-0004 decision 6).
 *
 * send_fn is injected, like S-038's SNTP call: the real MQTT sender
 * (P1-12) does not exist yet, and choosing the path (Ethernet or the ESP32,
 * ADR-0004 decision 8) is its job, not this module's.
 */

#ifndef TANK_COMMUNICATIONS_LOG_FORWARDER_H_
#define TANK_COMMUNICATIONS_LOG_FORWARDER_H_

#include <stddef.h>

#include "flash_log.h"

/* Returns 0 once the cloud has acknowledged every item, or a negative error
 * code if it has not (link down, timeout).
 */
typedef int (*tank_log_send_fn)(void *ctx, const struct tank_log_item *items, size_t count);

struct tank_log_forwarder {
	struct tank_flash_log *log;
	tank_log_send_fn send_fn;
	void *ctx;
	/* Caller-owned buffer of batch_cap items. */
	struct tank_log_item *batch;
	size_t batch_cap;
};

/*
 * Forward one batch. Returns the number of items delivered (0 when caught
 * up), the send_fn error if the cloud did not acknowledge, -EINVAL, or a
 * flash error.
 */
int tank_log_forwarder_poll(const struct tank_log_forwarder *fw);

#endif /* TANK_COMMUNICATIONS_LOG_FORWARDER_H_ */
