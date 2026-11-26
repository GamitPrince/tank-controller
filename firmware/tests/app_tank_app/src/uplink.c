/*
 * The application's uplink (S-061) on native_sim: scans keep being logged
 * while nothing answers on the ESP32 UART, an emulated ESP32 that confirms
 * each record drains the log, and the device ID is the factory ID in hex.
 */

#include <errno.h>
#include <string.h>

#include <zephyr/drivers/serial/uart_emul.h>
#include <zephyr/ztest.h>

#include "device_id.h"
#include "link_frame.h"
#include "link_receiver.h"
#include "scan_gen.h"
#include "tank_app.h"

#define UART_NODE DT_CHOSEN(tank_esp32_uart)
#define RING_SECTORS 16U
#define PERIOD_MS 50U
#define RUN_MS 400U
#define IDLE_MS 20U
#define RETRY_MS 100U
#define AGREEMENT_MS 1000U
#define DEV_ID "0123456789abcdef0123456789abcdef"

static const struct device *const uart_dev = DEVICE_DT_GET(UART_NODE);
static uint8_t boot_id[TANK_BOOT_ID_LEN] = {1};
static struct tank_app app;

/* The emulated ESP32: confirms every new record at once. */
static struct {
	struct tank_link_decoder dec;
	struct tank_link_receiver rx;
	uint32_t records;
} esp;

static void esp_reply(uint16_t seq)
{
	uint8_t out[TANK_LINK_FRAME_MAX];
	size_t len;

	zassert_ok(tank_link_receiver_confirm(&esp.rx, seq, out, sizeof(out), &len));
	zassert_equal(uart_emul_put_rx_data(uart_dev, out, len), len);
}

static void esp_hears(const struct device *d, size_t size, void *user_data)
{
	struct tank_link_msg msg;
	uint8_t byte;

	ARG_UNUSED(size);
	ARG_UNUSED(user_data);
	while (uart_emul_get_tx_data(d, &byte, 1U) == 1U) {
		if (tank_link_decoder_push(&esp.dec, byte, &msg) != TANK_LINK_RX_FRAME) {
			continue;
		}
		int action = tank_link_receiver_on_msg(&esp.rx, &msg);

		if (action == TANK_LINK_RECV_DELIVER) {
			esp.records++;
		}
		if (action != TANK_LINK_RECV_NONE) {
			esp_reply(msg.seq);
		}
	}
}

static struct tank_app_config config(void)
{
	return (struct tank_app_config){.boot_id = boot_id,
					.log = scan_gen_log_config(RING_SECTORS),
					.scan_period_ms = PERIOD_MS,
					.clock_agreement_limit_ms = AGREEMENT_MS,
					.esp32_uart = uart_dev,
					.device_id = DEV_ID,
					.uplink = {.idle_ms = IDLE_MS, .retry_ms = RETRY_MS}};
}

static void before_each(void *fixture)
{
	ARG_UNUSED(fixture);
	scan_gen_erase();
	memset(&esp, 0, sizeof(esp));
	tank_link_decoder_init(&esp.dec);
	tank_link_receiver_init(&esp.rx);
	uart_emul_flush_rx_data(uart_dev);
	uart_emul_flush_tx_data(uart_dev);
}

static void after_each(void *fixture)
{
	ARG_UNUSED(fixture);
	(void)tank_app_stop(&app);
	uart_emul_callback_tx_data_ready_set(uart_dev, NULL, NULL);
}

ZTEST_SUITE(app_uplink, NULL, NULL, before_each, after_each, NULL);

ZTEST(app_uplink, test_scans_are_logged_while_nothing_answers)
{
	const struct tank_app_config cfg = config();

	zassert_ok(tank_app_start(&app, &cfg));
	k_msleep(RUN_MS);
	zassert_true(tank_scan_service_stats(&app.scan)->scans >= RUN_MS / PERIOD_MS,
		     "scanning waited for the link");
	zassert_equal(tank_uplink_stats(&app.up)->confirmed, 0U);
	zassert_true(tank_uplink_stats(&app.up)->sent >= 1U, "the uplink tried");
}

ZTEST(app_uplink, test_an_esp32_that_confirms_drains_the_log)
{
	const struct tank_app_config cfg = config();
	struct tank_log_item item;
	uint32_t left = 0U;

	uart_emul_callback_tx_data_ready_set(uart_dev, esp_hears, NULL);
	zassert_ok(tank_app_start(&app, &cfg));
	k_msleep(RUN_MS);
	zassert_ok(tank_app_stop(&app));

	zassert_true(esp.records >= RUN_MS / PERIOD_MS / 2U, "ESP32 got %u", esp.records);
	zassert_equal(tank_uplink_stats(&app.up)->confirmed, esp.records);
	/* Count from the delivered position, not past what was read in flight. */
	tank_flash_log_rewind(&app.log);
	while (tank_flash_log_read_next(&app.log, &item) == 0) {
		left++;
	}
	zassert_true(left <= 2U, "%u records never forwarded", left);
}

ZTEST(app_uplink, test_a_uart_needs_a_device_id)
{
	struct tank_app_config cfg = config();

	cfg.device_id = NULL;
	zassert_equal(tank_app_start(&app, &cfg), -EINVAL);
}

ZTEST(app_uplink, test_device_id_is_the_factory_id_in_hex)
{
	const uint8_t uid[] = {0x00, 0x1f, 0xa0, 0xff};
	uint8_t too_long[TANK_DEVICE_ID_UID_MAX + 1U] = {0};
	char out[TANK_DEVICE_ID_BUF_LEN];

	zassert_ok(tank_device_id_format(uid, sizeof(uid), out, sizeof(out)));
	zassert_str_equal(out, "001fa0ff");
	zassert_equal(tank_device_id_format(uid, sizeof(uid), out, 2U * sizeof(uid)), -EINVAL,
		      "no room for the NUL");
	zassert_equal(tank_device_id_format(too_long, sizeof(too_long), out, sizeof(out)), -EINVAL);
	zassert_equal(tank_device_id_format(NULL, 1U, out, sizeof(out)), -EINVAL);
	zassert_equal(tank_device_id_format(uid, 0U, out, sizeof(out)), -EINVAL);
	zassert_equal(tank_device_id_format(uid, sizeof(uid), NULL, sizeof(out)), -EINVAL);

	zassert_ok(tank_device_id_read(out, sizeof(out)));
	zassert_true(strlen(out) >= 2U && strlen(out) <= 2U * TANK_DEVICE_ID_UID_MAX);
	zassert_equal(strspn(out, "0123456789abcdef"), strlen(out), "not lowercase hex: %s", out);
}
