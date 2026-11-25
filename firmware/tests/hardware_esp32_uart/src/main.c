/*
 * ztest suite for the FRDM-to-ESP32 UART driver glue (S-048), on Zephyr's
 * emulated UART: frames arriving in pieces, read timeouts, garbage and
 * overflow recovery, and exact bytes on the wire. The end-to-end path is in
 * end_to_end.c.
 */

#include <errno.h>
#include <string.h>

#include <zephyr/drivers/serial/uart_emul.h>
#include <zephyr/ztest.h>

#include "esp32_uart.h"
#include "link_frame.h"

#define UART_NODE DT_CHOSEN(tank_esp32_uart)
#define READ_TIMEOUT_MS 1000U
#define SHORT_TIMEOUT_MS 100U
#define TIMING_SLACK_MS 50U
#define LATE_PART_MS 20U
#define SETTLE_MS 10U
#define EMUL_CHUNK 256U
#define OVERFLOW_CHUNKS 3U
#define SEQ 0x1234U
#define CRC_FLIP 0x40U

static const struct device *const dev = DEVICE_DT_GET(UART_NODE);
static struct tank_esp32_uart uart;
static uint8_t frame[TANK_LINK_FRAME_MAX];
static size_t frame_len;
static size_t late_from;

/* A DELIVERED frame for SEQ, the kind the ESP32 sends. */
static void build_delivered(void)
{
	const uint8_t payload[TANK_LINK_DELIVERED_PAYLOAD_LEN] = {SEQ & 0xFFU, SEQ >> 8};
	const struct tank_link_msg msg = {
	    .type = TANK_LINK_DELIVERED, .payload = payload, .payload_len = sizeof(payload)};

	zassert_ok(tank_link_frame_encode(&msg, frame, sizeof(frame), &frame_len));
}

static void expect_delivered(const struct tank_link_msg *msg)
{
	zassert_equal(msg->type, TANK_LINK_DELIVERED);
	zassert_equal(msg->payload_len, TANK_LINK_DELIVERED_PAYLOAD_LEN);
	zassert_equal(msg->payload[0] | (msg->payload[1] << 8), SEQ);
}

static void put(const uint8_t *bytes, size_t len)
{
	zassert_equal(uart_emul_put_rx_data(dev, bytes, len), len);
}

static void send_late_part(struct k_timer *timer)
{
	ARG_UNUSED(timer);
	uart_emul_put_rx_data(dev, &frame[late_from], frame_len - late_from);
}

K_TIMER_DEFINE(late_timer, send_late_part, NULL);

static void before_each(void *fixture)
{
	ARG_UNUSED(fixture);
	uart_emul_callback_tx_data_ready_set(dev, NULL, NULL);
	uart_emul_flush_rx_data(dev);
	uart_emul_flush_tx_data(dev);
	zassert_ok(tank_esp32_uart_init(&uart, dev));
	build_delivered();
}

ZTEST_SUITE(esp32_uart, NULL, NULL, before_each, NULL, NULL);

ZTEST(esp32_uart, test_frame_in_pieces_is_returned_once_complete)
{
	struct tank_link_msg msg;

	late_from = frame_len / 2U;
	put(frame, late_from);
	zassert_equal(tank_esp32_uart_read(&uart, &msg, SETTLE_MS), -EAGAIN, "only half arrived");
	k_timer_start(&late_timer, K_MSEC(LATE_PART_MS), K_NO_WAIT);
	zassert_ok(tank_esp32_uart_read(&uart, &msg, READ_TIMEOUT_MS));
	expect_delivered(&msg);
	zassert_equal(tank_esp32_uart_stats(&uart)->frames, 1U);
	zassert_equal(tank_esp32_uart_stats(&uart)->rx_bytes, frame_len);
}

ZTEST(esp32_uart, test_read_times_out_after_its_timeout)
{
	struct tank_link_msg msg;
	int64_t start = k_uptime_get();
	int64_t took;

	zassert_equal(tank_esp32_uart_read(&uart, &msg, SHORT_TIMEOUT_MS), -EAGAIN);
	took = k_uptime_get() - start;
	zassert_true(took >= SHORT_TIMEOUT_MS, "returned after %lld ms", took);
	zassert_true(took < SHORT_TIMEOUT_MS + TIMING_SLACK_MS, "returned after %lld ms", took);
}

ZTEST(esp32_uart, test_garbage_and_a_bad_frame_are_skipped)
{
	static const uint8_t garbage[] = {0x11U, 0x22U, 0x00U};
	uint8_t bad[TANK_LINK_FRAME_MAX];
	struct tank_link_msg msg;

	memcpy(bad, frame, frame_len);
	bad[frame_len - 2U] ^= CRC_FLIP;
	put(garbage, sizeof(garbage));
	put(bad, frame_len);
	put(frame, frame_len);
	zassert_ok(tank_esp32_uart_read(&uart, &msg, READ_TIMEOUT_MS));
	expect_delivered(&msg);
	zassert_equal(tank_esp32_uart_stats(&uart)->rejected, 2U);
}

ZTEST(esp32_uart, test_overflow_is_counted_and_the_next_frame_arrives)
{
	static const uint8_t delimiter = 0x00U;
	uint8_t noise[EMUL_CHUNK];
	struct tank_link_msg msg;

	memset(noise, 0x55, sizeof(noise));
	for (uint32_t i = 0U; i < OVERFLOW_CHUNKS; i++) {
		put(noise, sizeof(noise));
		k_msleep(SETTLE_MS);
	}
	zassert_equal(tank_esp32_uart_stats(&uart)->rx_dropped,
		      OVERFLOW_CHUNKS * EMUL_CHUNK - TANK_ESP32_UART_RX_RING);
	zassert_equal(tank_esp32_uart_read(&uart, &msg, SETTLE_MS), -EAGAIN);
	put(&delimiter, 1U);
	put(frame, frame_len);
	zassert_ok(tank_esp32_uart_read(&uart, &msg, READ_TIMEOUT_MS));
	expect_delivered(&msg);
}

ZTEST(esp32_uart, test_write_puts_exactly_the_frame_on_the_wire)
{
	uint8_t wire[TANK_LINK_FRAME_MAX];

	zassert_ok(tank_esp32_uart_write(&uart, frame, frame_len));
	zassert_equal(uart_emul_get_tx_data(dev, wire, sizeof(wire)), frame_len);
	zassert_mem_equal(wire, frame, frame_len);
}

ZTEST(esp32_uart, test_clock_and_bad_arguments)
{
	struct tank_link_msg msg;
	uint32_t before = k_uptime_get_32();

	zassert_true(tank_esp32_uart_now(NULL) - before < TIMING_SLACK_MS);
	zassert_equal(tank_esp32_uart_init(NULL, dev), -EINVAL);
	zassert_equal(tank_esp32_uart_init(&uart, NULL), -EINVAL);
	zassert_equal(tank_esp32_uart_read(NULL, &msg, 0U), -EINVAL);
	zassert_equal(tank_esp32_uart_read(&uart, NULL, 0U), -EINVAL);
	zassert_equal(tank_esp32_uart_write(NULL, frame, 1U), -EINVAL);
	zassert_equal(tank_esp32_uart_write(&uart, NULL, 1U), -EINVAL);
	zassert_ok(tank_esp32_uart_write(&uart, NULL, 0U));
	zassert_is_null(tank_esp32_uart_stats(NULL));
}
