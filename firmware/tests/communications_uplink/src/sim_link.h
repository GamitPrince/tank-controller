/*
 * A simulated FRDM-to-ESP32 UART link for the uplink tests (S-045).
 *
 * The far end is the real S-043 link_receiver standing in for the ESP32: it
 * confirms each new RECORD at once, as if the cloud had acknowledged it,
 * and logs the length and CRC-16 of every record it passes up. The link can
 * drop RECORDs or DELIVEREDs, go dead (at once or part way through a
 * batch), fail a read, and send noise frames.
 * Time is a simulated millisecond clock that a read advances when it waits.
 */

#ifndef TANK_TEST_SIM_LINK_H_
#define TANK_TEST_SIM_LINK_H_

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "link_frame.h"
#include "link_receiver.h"

#define SIM_LOG_MAX 64U

struct sim_link {
	uint32_t clock_ms;
	/* Faults, set by a test. */
	uint32_t drop_records;
	uint32_t drop_delivered;
	bool dead;
	/* When non-zero, the link goes dead once this many frames got through. */
	uint32_t dead_after;
	int read_error;
	/* When non-zero, a read that would wait returns a frame this much later. */
	uint32_t noise_every_ms;
	/* What the ESP32 passed up, in order: frames, and the records inside them. */
	uint32_t delivered;
	uint32_t records;
	uint16_t log_crc[SIM_LOG_MAX];
	size_t log_len[SIM_LOG_MAX];
	struct tank_link_receiver rx;
};

extern struct sim_link sim;

void sim_link_reset(void);

/* The uplink's write_fn, read_fn and now_fn; ctx is ignored. */
int sim_link_write(void *ctx, const uint8_t *bytes, size_t len);
int sim_link_read(void *ctx, struct tank_link_msg *msg, uint32_t timeout_ms);
uint32_t sim_link_now(void *ctx);

#endif /* TANK_TEST_SIM_LINK_H_ */
