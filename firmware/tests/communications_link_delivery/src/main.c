/*
 * Tests for delivery confirmation on the FRDM-to-ESP32 UART link (S-043):
 * the stop-and-wait sender.
 */

#include <errno.h>
#include <string.h>
#include <zephyr/ztest.h>

#include "link_frame.h"
#include "link_sender.h"

#define TIMEOUT_MS 3000U
#define ATTEMPTS 3U
#define SEQ_WRAP 65536U
/* Less than one timeout before the 32-bit millisecond counter wraps. */
#define CLOCK_NEAR_WRAP 0xFFFFFF00U

/* Fake UART: keeps the last frame written and can be told to fail. */
struct fake_uart {
	uint8_t last[TANK_LINK_FRAME_MAX];
	size_t last_len;
	unsigned int writes;
	int fail_with;
};

static struct fake_uart uart;
static struct tank_link_sender sender;
static struct tank_link_decoder dec;
static const uint8_t payload[] = {0x00U, 0xA1U, 0x01U, 0x02U};

static int fake_write(void *ctx, const uint8_t *bytes, size_t len)
{
	struct fake_uart *u = ctx;

	if (u->fail_with != 0) {
		return u->fail_with;
	}
	memcpy(u->last, bytes, len);
	u->last_len = len;
	u->writes++;
	return 0;
}

/* Decode the last frame written; it must be exactly one good frame. */
static struct tank_link_msg last_written(void)
{
	struct tank_link_msg msg = {0};
	enum tank_link_rx rx = TANK_LINK_RX_NEED_MORE;

	tank_link_decoder_init(&dec);
	for (size_t i = 0; i < uart.last_len; i++) {
		rx = tank_link_decoder_push(&dec, uart.last[i], &msg);
	}
	zassert_equal(rx, TANK_LINK_RX_FRAME, "last write is not a frame");
	return msg;
}

static struct tank_link_msg delivered(uint16_t seq, uint8_t *buf)
{
	const struct tank_link_msg msg = {
	    .type = TANK_LINK_DELIVERED,
	    .seq = 0U,
	    .payload = buf,
	    .payload_len = TANK_LINK_DELIVERED_PAYLOAD_LEN,
	};

	buf[0] = (uint8_t)(seq & 0xFFU);
	buf[1] = (uint8_t)(seq >> 8);
	return msg;
}

static int confirm(uint16_t seq)
{
	uint8_t buf[TANK_LINK_DELIVERED_PAYLOAD_LEN];
	const struct tank_link_msg msg = delivered(seq, buf);

	return tank_link_sender_on_msg(&sender, &msg);
}

static void before_each(void *fixture)
{
	const struct tank_link_sender_config cfg = {
	    .ack_timeout_ms = TIMEOUT_MS,
	    .max_attempts = ATTEMPTS,
	};

	ARG_UNUSED(fixture);
	memset(&uart, 0, sizeof(uart));
	zassert_ok(tank_link_sender_init(&sender, &cfg, fake_write, &uart));
}

ZTEST_SUITE(link_sender, NULL, NULL, before_each, NULL, NULL);

ZTEST(link_sender, test_default_config_matches_spec)
{
	const struct tank_link_sender_config cfg = tank_link_sender_default_config();

	zassert_equal(cfg.ack_timeout_ms, TANK_LINK_ACK_TIMEOUT_MS);
	zassert_equal(cfg.max_attempts, TANK_LINK_MAX_ATTEMPTS);
}

ZTEST(link_sender, test_init_rejects_bad_arguments)
{
	struct tank_link_sender_config cfg = tank_link_sender_default_config();

	zassert_equal(tank_link_sender_init(NULL, &cfg, fake_write, &uart), -EINVAL);
	zassert_equal(tank_link_sender_init(&sender, NULL, fake_write, &uart), -EINVAL);
	zassert_equal(tank_link_sender_init(&sender, &cfg, NULL, &uart), -EINVAL);
	cfg.ack_timeout_ms = 0U;
	zassert_equal(tank_link_sender_init(&sender, &cfg, fake_write, &uart), -EINVAL);
	cfg = tank_link_sender_default_config();
	cfg.max_attempts = 0U;
	zassert_equal(tank_link_sender_init(&sender, &cfg, fake_write, &uart), -EINVAL);
}

ZTEST(link_sender, test_confirmed_record_frees_sender_and_next_uses_next_seq)
{
	struct tank_link_msg msg;

	zassert_ok(tank_link_sender_send(&sender, payload, sizeof(payload), 0U));
	msg = last_written();
	zassert_equal(msg.type, TANK_LINK_RECORD);
	zassert_equal(msg.seq, 0U);
	zassert_equal(msg.payload_len, sizeof(payload));
	zassert_mem_equal(msg.payload, payload, sizeof(payload));
	zassert_true(tank_link_sender_busy(&sender));

	zassert_equal(confirm(0U), TANK_LINK_SEND_CONFIRMED);
	zassert_false(tank_link_sender_busy(&sender));
	zassert_ok(tank_link_sender_send(&sender, payload, sizeof(payload), 10U));
	zassert_equal(last_written().seq, 1U);
	zassert_equal(tank_link_sender_stats(&sender)->sent, 2U);
	zassert_equal(tank_link_sender_stats(&sender)->confirmed, 1U);
}

ZTEST(link_sender, test_send_while_in_flight_is_busy_and_writes_nothing)
{
	zassert_ok(tank_link_sender_send(&sender, payload, sizeof(payload), 0U));
	zassert_equal(tank_link_sender_send(&sender, payload, sizeof(payload), 1U), -EBUSY);
	zassert_equal(uart.writes, 1U);
}

ZTEST(link_sender, test_send_rejects_bad_arguments)
{
	static uint8_t big[TANK_LINK_PAYLOAD_MAX + 1U];

	zassert_equal(tank_link_sender_send(NULL, payload, sizeof(payload), 0U), -EINVAL);
	zassert_equal(tank_link_sender_send(&sender, big, sizeof(big), 0U), -EINVAL);
	zassert_equal(uart.writes, 0U);
	zassert_false(tank_link_sender_busy(&sender));
}

ZTEST(link_sender, test_write_failure_is_returned_and_seq_not_used)
{
	uart.fail_with = -EIO;
	zassert_equal(tank_link_sender_send(&sender, payload, sizeof(payload), 0U), -EIO);
	zassert_false(tank_link_sender_busy(&sender));

	uart.fail_with = 0;
	zassert_ok(tank_link_sender_send(&sender, payload, sizeof(payload), 0U));
	zassert_equal(last_written().seq, 0U);
}

ZTEST(link_sender, test_lost_ack_retransmits_same_frame_until_confirmed)
{
	uint8_t first[TANK_LINK_FRAME_MAX];
	size_t first_len;

	zassert_ok(tank_link_sender_send(&sender, payload, sizeof(payload), 0U));
	memcpy(first, uart.last, uart.last_len);
	first_len = uart.last_len;

	zassert_ok(tank_link_sender_poll(&sender, TIMEOUT_MS - 1U));
	zassert_equal(uart.writes, 1U, "retransmitted before the timeout");
	zassert_ok(tank_link_sender_poll(&sender, TIMEOUT_MS));
	zassert_equal(uart.writes, 2U);
	zassert_equal(uart.last_len, first_len);
	zassert_mem_equal(uart.last, first, first_len);

	zassert_equal(confirm(0U), TANK_LINK_SEND_CONFIRMED);
	zassert_ok(tank_link_sender_poll(&sender, 10U * TIMEOUT_MS));
	zassert_equal(uart.writes, 2U, "wrote after confirmation");
	zassert_equal(tank_link_sender_stats(&sender)->retransmitted, 1U);
}

ZTEST(link_sender, test_gives_up_after_max_attempts_then_uses_new_seq)
{
	uint32_t now = 0U;

	zassert_ok(tank_link_sender_send(&sender, payload, sizeof(payload), now));
	for (unsigned int i = 1U; i < ATTEMPTS; i++) {
		now += TIMEOUT_MS;
		zassert_ok(tank_link_sender_poll(&sender, now));
	}
	zassert_equal(uart.writes, ATTEMPTS);
	now += TIMEOUT_MS;
	zassert_equal(tank_link_sender_poll(&sender, now), -ETIMEDOUT);
	zassert_false(tank_link_sender_busy(&sender));
	zassert_equal(uart.writes, ATTEMPTS, "wrote when giving up");
	zassert_equal(tank_link_sender_stats(&sender)->given_up, 1U);

	zassert_equal(confirm(0U), 0, "late ack confirmed a dropped record");
	zassert_ok(tank_link_sender_send(&sender, payload, sizeof(payload), now));
	zassert_equal(last_written().seq, 1U);
}

ZTEST(link_sender, test_retransmit_write_failure_still_counts_attempt)
{
	uint32_t now = 0U;

	zassert_ok(tank_link_sender_send(&sender, payload, sizeof(payload), now));
	uart.fail_with = -EIO;
	for (unsigned int i = 1U; i < ATTEMPTS; i++) {
		now += TIMEOUT_MS;
		zassert_equal(tank_link_sender_poll(&sender, now), -EIO);
	}
	now += TIMEOUT_MS;
	zassert_equal(tank_link_sender_poll(&sender, now), -ETIMEDOUT);
	zassert_false(tank_link_sender_busy(&sender));
}

ZTEST(link_sender, test_stale_and_malformed_acks_do_not_confirm)
{
	uint8_t buf[TANK_LINK_DELIVERED_PAYLOAD_LEN];
	struct tank_link_msg msg = delivered(0U, buf);
	const struct tank_link_msg record = {.type = TANK_LINK_RECORD, .seq = 0U};

	zassert_equal(confirm(0U), 0, "ack with nothing in flight");
	zassert_ok(tank_link_sender_send(&sender, payload, sizeof(payload), 0U));
	zassert_equal(confirm(7U), 0, "ack for another seq");
	msg.payload_len = 1U;
	zassert_equal(tank_link_sender_on_msg(&sender, &msg), 0, "short ack");
	msg.payload_len = TANK_LINK_DELIVERED_PAYLOAD_LEN;
	msg.payload = NULL;
	zassert_equal(tank_link_sender_on_msg(&sender, &msg), 0, "ack without payload");
	zassert_equal(tank_link_sender_stats(&sender)->stale_acks, 4U);

	zassert_equal(tank_link_sender_on_msg(&sender, &record), 0, "other type");
	zassert_equal(tank_link_sender_on_msg(&sender, NULL), 0);
	zassert_equal(tank_link_sender_on_msg(NULL, &record), 0);
	zassert_equal(tank_link_sender_stats(&sender)->stale_acks, 4U);
	zassert_true(tank_link_sender_busy(&sender));
}

ZTEST(link_sender, test_seq_wraps_from_65535_to_0)
{
	for (uint32_t i = 0U; i < SEQ_WRAP; i++) {
		zassert_ok(tank_link_sender_send(&sender, payload, sizeof(payload), 0U));
		zassert_equal(confirm((uint16_t)i), TANK_LINK_SEND_CONFIRMED);
	}
	zassert_ok(tank_link_sender_send(&sender, payload, sizeof(payload), 0U));
	zassert_equal(last_written().seq, 0U);
	zassert_equal(confirm(0U), TANK_LINK_SEND_CONFIRMED);
}

ZTEST(link_sender, test_timeout_survives_clock_wrap)
{
	const uint32_t start = CLOCK_NEAR_WRAP;

	zassert_ok(tank_link_sender_send(&sender, payload, sizeof(payload), start));
	zassert_ok(tank_link_sender_poll(&sender, start + TIMEOUT_MS - 1U));
	zassert_equal(uart.writes, 1U);
	zassert_ok(tank_link_sender_poll(&sender, start + TIMEOUT_MS));
	zassert_equal(uart.writes, 2U);
}

ZTEST(link_sender, test_null_sender_is_harmless)
{
	zassert_ok(tank_link_sender_poll(NULL, 0U));
	zassert_false(tank_link_sender_busy(NULL));
	zassert_is_null(tank_link_sender_stats(NULL));
	zassert_ok(tank_link_sender_poll(&sender, 0U), "idle poll");
}
