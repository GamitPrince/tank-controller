/*
 * The ESP32 end of the FRDM-to-ESP32 UART link (S-047, P1-12; ADR-0004
 * decisions 3 to 5, ADR-0006).
 *
 * UART bytes go in one at a time. Each new RECORD's payload is passed to
 * record_fn once. The upper layer (later MQTT) calls
 * tank_link_endpoint_confirm() when the cloud has acknowledged the record,
 * and only then is DELIVERED written back to the FRDM (S-043). A RECORD the
 * FRDM resends after a lost DELIVERED gets its DELIVERED again; one resent
 * before it was confirmed is dropped, because it is already with the upper
 * layer.
 *
 * If the upper layer cannot take a record it simply never confirms it. The
 * FRDM gives up, keeps the record in its flash log and later sends it again
 * with a new seq, which this endpoint passes up as new.
 *
 * Phase 1: the only frame this side writes is DELIVERED, which carries a
 * sequence number and nothing else. Nothing here commands the FRDM or the
 * plant.
 *
 * Standard C only, built on the shared link library in
 * firmware/src/communications/, so it is tested on a laptop with Unity.
 */

#ifndef TANK_ESP32_LINK_ENDPOINT_H_
#define TANK_ESP32_LINK_ENDPOINT_H_

#include <stddef.h>
#include <stdint.h>

#include "link_frame.h"
#include "link_receiver.h"

/* Number of decoder rejection reasons (enum tank_link_rx, -1 to -6). */
#define TANK_LINK_ENDPOINT_REJECT_REASONS 6U

/* A new RECORD for the upper layer; payload is valid only during the call. */
typedef void (*tank_link_record_fn)(void *ctx, uint16_t seq, const uint8_t *payload, size_t len);

/* Writes a whole frame to the UART. Returns 0 or a negative error. */
typedef int (*tank_link_endpoint_write_fn)(void *ctx, const uint8_t *bytes, size_t len);

struct tank_link_endpoint_stats {
	uint32_t frames;
	/* Indexed by -(enum tank_link_rx) - 1: bad COBS, bad CRC, too short,
	 * too long, bad version, bad type.
	 */
	uint32_t rejected[TANK_LINK_ENDPOINT_REJECT_REASONS];
	/* Well-formed frames that are not RECORDs. */
	uint32_t ignored;
	uint32_t records;
	uint32_t duplicates;
	uint32_t confirms_written;
};

/* Treat the fields as private; read the counters through stats. */
struct tank_link_endpoint {
	struct tank_link_decoder dec;
	struct tank_link_receiver rx;
	tank_link_record_fn record_fn;
	tank_link_endpoint_write_fn write_fn;
	void *ctx;
	struct tank_link_endpoint_stats stats;
};

/* Returns 0, or -EINVAL for a NULL argument. */
int tank_link_endpoint_init(struct tank_link_endpoint *ep, tank_link_record_fn record_fn,
			    tank_link_endpoint_write_fn write_fn, void *ctx);

/*
 * Feed one byte from the UART. Returns 0, -EINVAL for a NULL endpoint, or
 * the write_fn error when re-sending a DELIVERED failed (the FRDM resends
 * and the DELIVERED is tried again).
 */
int tank_link_endpoint_push(struct tank_link_endpoint *ep, uint8_t byte);

/*
 * The cloud has the record with this seq: write its DELIVERED. Returns 0,
 * -EINVAL for a NULL endpoint or a seq other than the last record passed
 * up, or the write_fn error.
 */
int tank_link_endpoint_confirm(struct tank_link_endpoint *ep, uint16_t seq);

const struct tank_link_endpoint_stats *
tank_link_endpoint_stats(const struct tank_link_endpoint *ep);

#endif /* TANK_ESP32_LINK_ENDPOINT_H_ */
