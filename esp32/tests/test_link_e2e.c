/*
 * End-to-end Unity test for the UART link (S-047): the FRDM's stop-and-wait
 * link_sender (S-043) joined to the ESP32's link_endpoint, with a simulated
 * wire that can lose a RECORD or a DELIVERED. The upper layer confirms each
 * record as soon as it is passed up, as if the cloud had acknowledged it.
 *
 * Bytes the FRDM writes are held on the wire and delivered after the
 * sender's call returns, as a real UART would: a DELIVERED must not reach
 * the sender while it is still inside send().
 */

#include <errno.h>
#include <stdbool.h>
#include <string.h>
#include <unity.h>

#include "link_endpoint.h"
#include "link_frame.h"
#include "link_sender.h"

#define TIMEOUT_MS 3000U
#define ATTEMPTS 3U
#define RECORDS 3U

static struct tank_link_sender frdm;
static struct tank_link_endpoint esp;
static struct tank_link_decoder frdm_dec;

static struct {
	unsigned int drop_records;
	unsigned int drop_delivered;
	unsigned int passed_up;
	uint16_t up_seq[RECORDS];
	uint16_t last_up_seq;
	bool confirmed;
	uint8_t pending[TANK_LINK_FRAME_MAX];
	size_t pending_len;
} wire;

static void on_record(void *ctx, uint16_t seq, const uint8_t *payload, size_t len)
{
	(void)ctx;
	(void)payload;
	(void)len;
	if (wire.passed_up < RECORDS) {
		wire.up_seq[wire.passed_up] = seq;
	}
	wire.last_up_seq = seq;
	wire.passed_up++;
}

/* ESP32 to FRDM: decode and offer each DELIVERED to the sender. */
static int esp_write(void *ctx, const uint8_t *bytes, size_t len)
{
	struct tank_link_msg msg;

	(void)ctx;
	if (wire.drop_delivered > 0U) {
		wire.drop_delivered--;
		return 0;
	}
	for (size_t i = 0U; i < len; i++) {
		if (tank_link_decoder_push(&frdm_dec, bytes[i], &msg) == TANK_LINK_RX_FRAME &&
		    tank_link_sender_on_msg(&frdm, &msg) == TANK_LINK_SEND_CONFIRMED) {
			wire.confirmed = true;
		}
	}
	return 0;
}

/* FRDM to ESP32: the frame goes on the wire unless it is lost. */
static int frdm_write(void *ctx, const uint8_t *bytes, size_t len)
{
	(void)ctx;
	if (wire.drop_records > 0U) {
		wire.drop_records--;
		return 0;
	}
	memcpy(wire.pending, bytes, len);
	wire.pending_len = len;
	return 0;
}

/* Deliver what is on the wire to the ESP32; the cloud acknowledges at once. */
static void deliver_wire(void)
{
	unsigned int before = wire.passed_up;

	for (size_t i = 0U; i < wire.pending_len; i++) {
		TEST_ASSERT_EQUAL_INT(0, tank_link_endpoint_push(&esp, wire.pending[i]));
	}
	wire.pending_len = 0U;
	if (wire.passed_up != before) {
		TEST_ASSERT_EQUAL_INT(0, tank_link_endpoint_confirm(&esp, wire.last_up_seq));
	}
}

/* Send one record and poll until the FRDM sees it confirmed or gives up. */
static int send_one(uint8_t tag)
{
	const uint8_t payload[] = {0xA1U, tag};
	uint32_t now = 0U;
	int rc = 0;

	wire.confirmed = false;
	TEST_ASSERT_EQUAL_INT(0, tank_link_sender_send(&frdm, payload, sizeof(payload), now));
	deliver_wire();
	while (!wire.confirmed && rc == 0) {
		now += TIMEOUT_MS;
		rc = tank_link_sender_poll(&frdm, now);
		deliver_wire();
	}
	return rc;
}

void setUp(void)
{
	const struct tank_link_sender_config cfg = {.ack_timeout_ms = TIMEOUT_MS,
						    .max_attempts = ATTEMPTS};

	memset(&wire, 0, sizeof(wire));
	tank_link_decoder_init(&frdm_dec);
	TEST_ASSERT_EQUAL_INT(0, tank_link_sender_init(&frdm, &cfg, frdm_write, NULL));
	TEST_ASSERT_EQUAL_INT(0, tank_link_endpoint_init(&esp, on_record, esp_write, NULL));
}

void tearDown(void)
{
}

static void test_records_are_confirmed_in_order(void)
{
	for (uint8_t i = 0U; i < RECORDS; i++) {
		TEST_ASSERT_EQUAL_INT(0, send_one(i));
		TEST_ASSERT_TRUE(wire.confirmed);
	}
	TEST_ASSERT_EQUAL_UINT(RECORDS, wire.passed_up);
	for (uint16_t i = 0U; i < RECORDS; i++) {
		TEST_ASSERT_EQUAL_UINT16(i, wire.up_seq[i]);
	}
	TEST_ASSERT_EQUAL_UINT32(0U, tank_link_sender_stats(&frdm)->retransmitted);
}

static void test_lost_record_and_lost_delivered_still_confirm_once(void)
{
	wire.drop_records = 1U;
	wire.drop_delivered = 1U;
	TEST_ASSERT_EQUAL_INT(0, send_one(0U));
	TEST_ASSERT_TRUE(wire.confirmed);
	TEST_ASSERT_EQUAL_UINT(1U, wire.passed_up);
	TEST_ASSERT_EQUAL_UINT32(2U, tank_link_sender_stats(&frdm)->retransmitted);
	TEST_ASSERT_EQUAL_UINT32(1U, tank_link_endpoint_stats(&esp)->duplicates);
	TEST_ASSERT_EQUAL_UINT32(2U, tank_link_endpoint_stats(&esp)->confirms_written);
}

static void test_dead_link_gives_up_without_passing_anything_up(void)
{
	wire.drop_records = ATTEMPTS;
	TEST_ASSERT_EQUAL_INT(-ETIMEDOUT, send_one(0U));
	TEST_ASSERT_FALSE(wire.confirmed);
	TEST_ASSERT_EQUAL_UINT(0U, wire.passed_up);
}

int main(void)
{
	UNITY_BEGIN();
	RUN_TEST(test_records_are_confirmed_in_order);
	RUN_TEST(test_lost_record_and_lost_delivered_still_confirm_once);
	RUN_TEST(test_dead_link_gives_up_without_passing_anything_up);
	return UNITY_END();
}
