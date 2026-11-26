/*
 * End to end on native_sim (S-048): a real flash log, log_forwarder (S-039),
 * the uplink (S-045) and the UART driver glue, talking over Zephyr's
 * emulated UART to an emulated ESP32 built from S-043's link_receiver. The
 * ESP32 side confirms each new record at once, as if the cloud had it, and
 * can lose a DELIVERED.
 */

#include <string.h>

#include <zephyr/drivers/serial/uart_emul.h>
#include <zephyr/ztest.h>

#include "esp32_uart.h"
#include "flash_log.h"
#include "link_frame.h"
#include "link_receiver.h"
#include "link_sender.h"
#include "log_forwarder.h"
#include "scan_gen.h"
#include "uplink.h"

#define UART_NODE DT_CHOSEN(tank_esp32_uart)
#define DEV_ID "tank-test-01"
#define RING_SECTORS 4U
#define BATCH_CAP 8U
#define BATCH_SCANS 5U
#define ACK_TIMEOUT_MS 200U
#define ATTEMPTS 3U
#define BOOT 0U

static const struct device *const dev = DEVICE_DT_GET(UART_NODE);
static struct tank_esp32_uart uart;
static struct tank_uplink up;
static struct tank_flash_log log;
static struct tank_log_item batch[BATCH_CAP];

/* The emulated ESP32. */
static struct {
	struct tank_link_decoder dec;
	struct tank_link_receiver rx;
	/* Frames passed up, and the records inside them (S-063). */
	uint32_t frames;
	uint32_t records;
	uint32_t drop_delivered;
} esp;

static const struct tank_log_forwarder fw = {
    .log = &log, .send_fn = tank_uplink_send, .ctx = &up, .batch = batch, .batch_cap = BATCH_CAP};

static void reply(uint16_t seq)
{
	uint8_t out[TANK_LINK_FRAME_MAX];
	size_t len;

	zassert_ok(tank_link_receiver_confirm(&esp.rx, seq, out, sizeof(out), &len));
	if (esp.drop_delivered > 0U) {
		esp.drop_delivered--;
		return;
	}
	zassert_equal(uart_emul_put_rx_data(dev, out, len), len);
}

static void on_frame(const struct tank_link_msg *msg)
{
	int action = tank_link_receiver_on_msg(&esp.rx, msg);

	if (action == TANK_LINK_RECV_DELIVER) {
		esp.frames++;
		/* A batch's CBOR array header holds its record count. */
		esp.records += msg->payload[0] & 0x1FU;
	}
	if (action != TANK_LINK_RECV_NONE) {
		reply(msg->seq);
	}
}

/* Bytes the FRDM wrote, one poll_out at a time. */
static void esp_hears(const struct device *d, size_t size, void *user_data)
{
	struct tank_link_msg msg;
	uint8_t byte;

	ARG_UNUSED(size);
	ARG_UNUSED(user_data);
	while (uart_emul_get_tx_data(d, &byte, 1U) == 1U) {
		if (tank_link_decoder_push(&esp.dec, byte, &msg) == TANK_LINK_RX_FRAME) {
			on_frame(&msg);
		}
	}
}

static void before_each(void *fixture)
{
	const struct tank_link_sender_config link_cfg = {.ack_timeout_ms = ACK_TIMEOUT_MS,
							 .max_attempts = ATTEMPTS};
	const struct tank_uplink_io io = {.write_fn = tank_esp32_uart_write,
					  .read_fn = tank_esp32_uart_read,
					  .now_fn = tank_esp32_uart_now,
					  .ctx = &uart};
	struct tank_flash_log_config cfg = scan_gen_log_config(RING_SECTORS);
	struct tank_scan s;

	ARG_UNUSED(fixture);
	memset(&esp, 0, sizeof(esp));
	tank_link_decoder_init(&esp.dec);
	tank_link_receiver_init(&esp.rx);
	uart_emul_flush_rx_data(dev);
	uart_emul_flush_tx_data(dev);
	uart_emul_callback_tx_data_ready_set(dev, esp_hears, NULL);
	zassert_ok(tank_esp32_uart_init(&uart, dev));
	zassert_ok(tank_uplink_init(&up, DEV_ID, &link_cfg, &io));

	scan_gen_erase();
	zassert_ok(tank_flash_log_mount(&log, &cfg));
	for (uint32_t seq = 1U; seq <= BATCH_SCANS; seq++) {
		scan_gen(&s, BOOT, seq, false);
		zassert_ok(tank_flash_log_append(&log, &s));
	}
}

static void after_each(void *fixture)
{
	ARG_UNUSED(fixture);
	uart_emul_callback_tx_data_ready_set(dev, NULL, NULL);
}

ZTEST_SUITE(esp32_uart_end_to_end, NULL, NULL, before_each, after_each, NULL);

ZTEST(esp32_uart_end_to_end, test_batch_is_confirmed_over_the_uart)
{
	zassert_equal(tank_log_forwarder_poll(&fw), BATCH_SCANS);
	zassert_equal(tank_log_forwarder_poll(&fw), 0, "the batch was acked");
	zassert_equal(esp.records, BATCH_SCANS);
	zassert_equal(esp.frames, 1U, "five records travel in one frame");
	zassert_equal(tank_uplink_stats(&up)->confirmed, 1U);
	zassert_equal(tank_link_sender_stats(&up.sender)->retransmitted, 0U);
	zassert_equal(tank_esp32_uart_stats(&uart)->frames, 1U, "one DELIVERED came back");
}

ZTEST(esp32_uart_end_to_end, test_lost_delivered_is_recovered_once)
{
	esp.drop_delivered = 1U;
	zassert_equal(tank_log_forwarder_poll(&fw), BATCH_SCANS);
	zassert_equal(esp.records, BATCH_SCANS, "each record passed up once");
	zassert_equal(esp.frames, 1U);
	zassert_equal(tank_link_receiver_stats(&esp.rx)->duplicates, 1U);
	zassert_equal(tank_link_sender_stats(&up.sender)->retransmitted, 1U);
}
