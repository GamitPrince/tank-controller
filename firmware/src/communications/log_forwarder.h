/*
 * Forward the flash log to the cloud, oldest first (S-039, P1-14).
 *
 * Each poll reads up to one batch of undelivered items from the flash log
 * (firmware/src/record/flash_log.h) and hands them to send_fn. When send_fn
 * reports a cloud acknowledgement the batch is marked delivered; otherwise
 * it is rewound and resent on a later poll, so nothing is lost while the
 * link is down. When only the first items of a batch were acknowledged
 * (a stop-and-wait link that gave up part way, S-045), those are marked
 * delivered and only the rest is resent. Items keep the boot id, seq, up, tk and t they were logged
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

/*
 * Returns the number of leading items the cloud has acknowledged (1 to
 * count), or a negative error code when it acknowledged none (link down,
 * timeout). Any other value is a broken send_fn.
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
 * up; fewer than the batch when send_fn acknowledged only part of it), the
 * send_fn error if the cloud acknowledged none, -EINVAL for bad arguments
 * or a send_fn result outside 1 to count, or a flash error.
 */
int tank_log_forwarder_poll(const struct tank_log_forwarder *fw);

#endif /* TANK_COMMUNICATIONS_LOG_FORWARDER_H_ */
