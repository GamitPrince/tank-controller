/*
 * The FRDM's UART to the ESP32 communications helper (S-048, P1-12;
 * ADR-0004 decision 4).
 *
 * Gives the uplink (S-045) its read_fn, write_fn and now_fn on a real Zephyr
 * UART. Received bytes are moved by the UART interrupt into a ring buffer;
 * tank_esp32_uart_read() decodes them into link frames (S-042). Frames are
 * written with uart_poll_out(): a worst-case record frame is about 1 KB, some
 * 90 ms at 115200 baud, once per scan and only from the forwarder's thread.
 *
 * If the ring overflows the extra bytes are dropped and counted. The damaged
 * frame then fails its CRC, the decoder resynchronises at the next
 * delimiter, and S-043's resend recovers the record.
 *
 * Boot code finds the UART through the devicetree chosen node
 * `tank,esp32-uart`. Its instance, pins and baud rate (115200 8N1 for now)
 * belong in the FRDM board overlay, which waits on the EE's pin mapping
 * (ADR-0002).
 *
 * Phase 1: this module only moves bytes. Nothing received is acted on as a
 * command; the uplink reads back DELIVERED and nothing else.
 */

#ifndef TANK_HARDWARE_ESP32_UART_H_
#define TANK_HARDWARE_ESP32_UART_H_

#include <stddef.h>
#include <stdint.h>

#include <zephyr/device.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/ring_buffer.h>

#include "link_frame.h"

/* The ESP32 sends only short frames (DELIVERED) in Phase 1. */
#define TANK_ESP32_UART_RX_RING 512U

struct tank_esp32_uart_stats {
	uint32_t rx_bytes;
	/* Received bytes lost because the ring was full. */
	uint32_t rx_dropped;
	uint32_t frames;
	uint32_t rejected;
};

/* Treat the fields as private; read the counters through stats. */
struct tank_esp32_uart {
	const struct device *dev;
	struct ring_buf rx;
	uint8_t rx_mem[TANK_ESP32_UART_RX_RING];
	struct k_spinlock rx_lock;
	struct k_sem rx_sem;
	struct tank_link_decoder dec;
	struct tank_esp32_uart_stats stats;
};

/*
 * Returns 0, -EINVAL for a NULL argument, -ENODEV if the UART is not ready,
 * or the error from installing the interrupt callback.
 */
int tank_esp32_uart_init(struct tank_esp32_uart *u, const struct device *dev);

/*
 * A tank_uplink_read_fn; ctx is the struct tank_esp32_uart. Returns 0 with
 * *msg filled (its payload valid until the next call), -EAGAIN once
 * timeout_ms has passed without a whole frame, or -EINVAL.
 */
int tank_esp32_uart_read(void *ctx, struct tank_link_msg *msg, uint32_t timeout_ms);

/* A tank_link_write_fn. Returns 0, or -EINVAL for a NULL argument. */
int tank_esp32_uart_write(void *ctx, const uint8_t *bytes, size_t len);

/* A tank_uplink_now_fn: kernel uptime in milliseconds. */
uint32_t tank_esp32_uart_now(void *ctx);

const struct tank_esp32_uart_stats *tank_esp32_uart_stats(const struct tank_esp32_uart *u);

#endif /* TANK_HARDWARE_ESP32_UART_H_ */
