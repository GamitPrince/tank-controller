/*
 * The FRDM's UART to the ESP32 (S-048). See esp32_uart.h.
 */

#include "esp32_uart.h"

#include <errno.h>
#include <stdbool.h>

#include <zephyr/drivers/uart.h>

/* Bytes moved from the UART FIFO per read inside the interrupt. */
#define RX_CHUNK 16U

static void on_uart_irq(const struct device *dev, void *user_data)
{
	struct tank_esp32_uart *u = user_data;
	uint8_t chunk[RX_CHUNK];
	k_spinlock_key_t key;
	uint32_t stored;
	int n;

	uart_irq_update(dev);
	while (uart_irq_rx_ready(dev) > 0) {
		n = uart_fifo_read(dev, chunk, sizeof(chunk));
		if (n <= 0) {
			break;
		}
		key = k_spin_lock(&u->rx_lock);
		stored = ring_buf_put(&u->rx, chunk, (uint32_t)n);
		u->stats.rx_bytes += (uint32_t)n;
		u->stats.rx_dropped += (uint32_t)n - stored;
		k_spin_unlock(&u->rx_lock, key);
	}
	k_sem_give(&u->rx_sem);
}

int tank_esp32_uart_init(struct tank_esp32_uart *u, const struct device *dev)
{
	int err;

	if (u == NULL || dev == NULL) {
		return -EINVAL;
	}
	if (!device_is_ready(dev)) {
		return -ENODEV;
	}
	*u = (struct tank_esp32_uart){.dev = dev};
	ring_buf_init(&u->rx, sizeof(u->rx_mem), u->rx_mem);
	k_sem_init(&u->rx_sem, 0, 1);
	tank_link_decoder_init(&u->dec);
	err = uart_irq_callback_user_data_set(dev, on_uart_irq, u);
	if (err != 0) {
		return err;
	}
	uart_irq_rx_enable(dev);
	return 0;
}

/* Feed buffered bytes to the decoder; true once a whole frame is in *msg. */
static bool decode_buffered(struct tank_esp32_uart *u, struct tank_link_msg *msg)
{
	k_spinlock_key_t key;
	enum tank_link_rx rx;
	uint8_t byte;
	uint32_t got;

	for (;;) {
		key = k_spin_lock(&u->rx_lock);
		got = ring_buf_get(&u->rx, &byte, 1U);
		k_spin_unlock(&u->rx_lock, key);
		if (got == 0U) {
			return false;
		}
		rx = tank_link_decoder_push(&u->dec, byte, msg);
		if (rx == TANK_LINK_RX_FRAME) {
			u->stats.frames++;
			return true;
		}
		if (rx < 0) {
			u->stats.rejected++;
		}
	}
}

int tank_esp32_uart_read(void *ctx, struct tank_link_msg *msg, uint32_t timeout_ms)
{
	struct tank_esp32_uart *u = ctx;
	int64_t deadline;
	int64_t left;

	if (u == NULL || msg == NULL) {
		return -EINVAL;
	}
	deadline = k_uptime_get() + timeout_ms;
	for (;;) {
		if (decode_buffered(u, msg)) {
			return 0;
		}
		left = deadline - k_uptime_get();
		if (left <= 0) {
			return -EAGAIN;
		}
		(void)k_sem_take(&u->rx_sem, K_MSEC(left));
	}
}

int tank_esp32_uart_write(void *ctx, const uint8_t *bytes, size_t len)
{
	struct tank_esp32_uart *u = ctx;

	if (u == NULL || (bytes == NULL && len != 0U)) {
		return -EINVAL;
	}
	for (size_t i = 0U; i < len; i++) {
		uart_poll_out(u->dev, bytes[i]);
	}
	return 0;
}

uint32_t tank_esp32_uart_now(void *ctx)
{
	ARG_UNUSED(ctx);
	return k_uptime_get_32();
}

const struct tank_esp32_uart_stats *tank_esp32_uart_stats(const struct tank_esp32_uart *u)
{
	return (u == NULL) ? NULL : &u->stats;
}
