/*
 * Tests for delivery confirmation on the FRDM-to-ESP32 UART link (S-043):
 * the receiver on its own, then sender and receiver joined by a simulated
 * link that can drop or duplicate frames in either direction.
 */

#include <errno.h>
#include <string.h>
#include <zephyr/ztest.h>

#include "link_frame.h"
#include "link_receiver.h"
#include "link_sender.h"

#define TIMEOUT_MS 3000U
#define ATTEMPTS 3U
#define QUEUE_LEN 4U
#define SEQ_WRAP 65536U

static struct tank_link_receiver rx;
static uint8_t frame[TANK_LINK_FRAME_MAX];
static const uint8_t data_a[] = {0x00U, 0xA1U, 0x01U};
static const uint8_t data_b[] = {0x00U, 0xA1U, 0x02U};

static struct tank_link_msg record(uint16_t seq, const uint8_t *payload, size_t len)
{
	const struct tank_link_msg msg = {
	    .type = TANK_LINK_RECORD,
	    .seq = seq,
	    .payload = payload,
	    .payload_len = len,
	};

	return msg;
}

static int offer(uint16_t seq, const uint8_t *payload, size_t len)
{
	const struct tank_link_msg msg = record(seq, payload, len);

	return tank_link_receiver_on_msg(&rx, &msg);
}

static int confirm(uint16_t seq)
{
	size_t len;

	return tank_link_receiver_confirm(&rx, seq, frame, sizeof(frame), &len);
}

static void receiver_before(void *fixture)
{
	ARG_UNUSED(fixture);
	tank_link_receiver_init(&rx);
}

ZTEST_SUITE(link_receiver, NULL, NULL, receiver_before, NULL, NULL);

ZTEST(link_receiver, test_new_record_is_delivered_once)
{
	zassert_equal(offer(5U, data_a, sizeof(data_a)), TANK_LINK_RECV_DELIVER);
	zassert_equal(offer(5U, data_a, sizeof(data_a)), TANK_LINK_RECV_NONE,
		      "unconfirmed repeat must not be passed up or confirmed");
	zassert_equal(tank_link_receiver_stats(&rx)->accepted, 1U);
	zassert_equal(tank_link_receiver_stats(&rx)->duplicates, 1U);
}

ZTEST(link_receiver, test_repeat_of_confirmed_record_is_reconfirmed)
{
	zassert_equal(offer(5U, data_a, sizeof(data_a)), TANK_LINK_RECV_DELIVER);
	zassert_ok(confirm(5U));
	zassert_equal(offer(5U, data_a, sizeof(data_a)), TANK_LINK_RECV_RECONFIRM);
	zassert_ok(confirm(5U));
	zassert_equal(tank_link_receiver_stats(&rx)->accepted, 1U);
}

ZTEST(link_receiver, test_same_seq_with_other_payload_is_new)
{
	zassert_equal(offer(0U, data_a, sizeof(data_a)), TANK_LINK_RECV_DELIVER);
	zassert_ok(confirm(0U));
	zassert_equal(offer(0U, data_b, sizeof(data_b)), TANK_LINK_RECV_DELIVER,
		      "a FRDM reboot that restarts seq must not lose a record");
	zassert_equal(offer(0U, data_b, sizeof(data_b) - 1U), TANK_LINK_RECV_DELIVER,
		      "different length");
	zassert_equal(offer(0U, NULL, 0U), TANK_LINK_RECV_DELIVER, "empty payload");
	zassert_equal(tank_link_receiver_stats(&rx)->accepted, 4U);
}

ZTEST(link_receiver, test_new_seq_replaces_unconfirmed_record)
{
	zassert_equal(offer(1U, data_a, sizeof(data_a)), TANK_LINK_RECV_DELIVER);
	zassert_equal(offer(2U, data_a, sizeof(data_a)), TANK_LINK_RECV_DELIVER);
	zassert_equal(confirm(1U), -EINVAL, "only the last record can be confirmed");
	zassert_ok(confirm(2U));
}

ZTEST(link_receiver, test_confirm_builds_delivered_frame)
{
	struct tank_link_decoder dec;
	struct tank_link_msg msg = {0};
	enum tank_link_rx res = TANK_LINK_RX_NEED_MORE;
	size_t len;

	zassert_equal(offer(0x1234U, data_a, sizeof(data_a)), TANK_LINK_RECV_DELIVER);
	zassert_ok(tank_link_receiver_confirm(&rx, 0x1234U, frame, sizeof(frame), &len));
	tank_link_decoder_init(&dec);
	for (size_t i = 0; i < len; i++) {
		res = tank_link_decoder_push(&dec, frame[i], &msg);
	}
	zassert_equal(res, TANK_LINK_RX_FRAME);
	zassert_equal(msg.type, TANK_LINK_DELIVERED);
	zassert_equal(msg.payload_len, TANK_LINK_DELIVERED_PAYLOAD_LEN);
	zassert_equal(msg.payload[0], 0x34U);
	zassert_equal(msg.payload[1], 0x12U);
}

ZTEST(link_receiver, test_confirm_rejects_bad_requests)
{
	size_t len;

	zassert_equal(confirm(0U), -EINVAL, "nothing accepted yet");
	zassert_equal(offer(0U, data_a, sizeof(data_a)), TANK_LINK_RECV_DELIVER);
	zassert_equal(tank_link_receiver_confirm(NULL, 0U, frame, sizeof(frame), &len), -EINVAL);
	zassert_equal(tank_link_receiver_confirm(&rx, 0U, frame, 1U, &len), -ENOSPC);
	zassert_equal(offer(0U, data_a, sizeof(data_a)), TANK_LINK_RECV_NONE,
		      "a failed confirm must not count as confirmed");
}

ZTEST(link_receiver, test_other_types_and_bad_arguments)
{
	const struct tank_link_msg status = {.type = TANK_LINK_LINK_STATUS};
	const struct tank_link_msg bad = record(0U, NULL, 1U);

	zassert_equal(tank_link_receiver_on_msg(&rx, &status), TANK_LINK_RECV_NONE);
	zassert_equal(tank_link_receiver_on_msg(&rx, &bad), -EINVAL);
	zassert_equal(tank_link_receiver_on_msg(NULL, &status), -EINVAL);
	zassert_equal(tank_link_receiver_on_msg(&rx, NULL), -EINVAL);
	tank_link_receiver_init(NULL);
	zassert_is_null(tank_link_receiver_stats(NULL));
	zassert_equal(tank_link_receiver_stats(&rx)->accepted, 0U);
}

/* Simulated link: frames queue in each direction until pumped. */
struct queue {
	uint8_t frames[QUEUE_LEN][TANK_LINK_FRAME_MAX];
	size_t lens[QUEUE_LEN];
	size_t count;
};

static struct {
	struct tank_link_sender tx;
	struct tank_link_decoder esp_dec;
	struct tank_link_decoder frdm_dec;
	struct queue to_esp;
	struct queue to_frdm;
	unsigned int drop_records;
	unsigned int dup_records;
	unsigned int drop_acks;
	unsigned int passed_up;
	unsigned int confirmed;
} link;

static void enqueue(struct queue *q, const uint8_t *bytes, size_t len)
{
	zassert_true(q->count < QUEUE_LEN, "link queue full");
	memcpy(q->frames[q->count], bytes, len);
	q->lens[q->count] = len;
	q->count++;
}

static int wire_write(void *ctx, const uint8_t *bytes, size_t len)
{
	ARG_UNUSED(ctx);
	if (link.drop_records > 0U) {
		link.drop_records--;
		return 0;
	}
	enqueue(&link.to_esp, bytes, len);
	if (link.dup_records > 0U) {
		link.dup_records--;
		enqueue(&link.to_esp, bytes, len);
	}
	return 0;
}

/* ESP32 side: pass new records up and confirm them straight away. */
static void esp_handle(const struct tank_link_msg *msg)
{
	uint8_t ack[TANK_LINK_FRAME_MAX];
	size_t len;
	const int action = tank_link_receiver_on_msg(&rx, msg);

	if (action == TANK_LINK_RECV_DELIVER) {
		link.passed_up++;
	}
	if (action == TANK_LINK_RECV_NONE) {
		return;
	}
	zassert_ok(tank_link_receiver_confirm(&rx, msg->seq, ack, sizeof(ack), &len));
	if (link.drop_acks > 0U) {
		link.drop_acks--;
		return;
	}
	enqueue(&link.to_frdm, ack, len);
}

static void frdm_handle(const struct tank_link_msg *msg)
{
	if (tank_link_sender_on_msg(&link.tx, msg) == TANK_LINK_SEND_CONFIRMED) {
		link.confirmed++;
	}
}

static void drain(struct queue *q, struct tank_link_decoder *dec,
		  void (*handle)(const struct tank_link_msg *msg))
{
	struct tank_link_msg msg;

	for (size_t f = 0; f < q->count; f++) {
		for (size_t i = 0; i < q->lens[f]; i++) {
			if (tank_link_decoder_push(dec, q->frames[f][i], &msg) ==
			    TANK_LINK_RX_FRAME) {
				handle(&msg);
			}
		}
	}
	q->count = 0U;
}

static void pump(void)
{
	drain(&link.to_esp, &link.esp_dec, esp_handle);
	drain(&link.to_frdm, &link.frdm_dec, frdm_handle);
}

static void link_before(void *fixture)
{
	const struct tank_link_sender_config cfg = {
	    .ack_timeout_ms = TIMEOUT_MS,
	    .max_attempts = ATTEMPTS,
	};

	ARG_UNUSED(fixture);
	memset(&link, 0, sizeof(link));
	tank_link_decoder_init(&link.esp_dec);
	tank_link_decoder_init(&link.frdm_dec);
	tank_link_receiver_init(&rx);
	zassert_ok(tank_link_sender_init(&link.tx, &cfg, wire_write, NULL));
}

ZTEST_SUITE(link_delivery, NULL, NULL, link_before, NULL, NULL);

ZTEST(link_delivery, test_clean_delivery)
{
	zassert_ok(tank_link_sender_send(&link.tx, data_a, sizeof(data_a), 0U));
	pump();
	zassert_equal(link.passed_up, 1U);
	zassert_equal(link.confirmed, 1U);
	zassert_false(tank_link_sender_busy(&link.tx));
}

ZTEST(link_delivery, test_lost_record_is_recovered_once)
{
	link.drop_records = 1U;
	zassert_ok(tank_link_sender_send(&link.tx, data_a, sizeof(data_a), 0U));
	pump();
	zassert_equal(link.passed_up, 0U);
	zassert_ok(tank_link_sender_poll(&link.tx, TIMEOUT_MS));
	pump();
	zassert_equal(link.passed_up, 1U);
	zassert_equal(link.confirmed, 1U);
}

ZTEST(link_delivery, test_lost_ack_is_recovered_without_second_delivery)
{
	link.drop_acks = 1U;
	zassert_ok(tank_link_sender_send(&link.tx, data_a, sizeof(data_a), 0U));
	pump();
	zassert_equal(link.passed_up, 1U);
	zassert_true(tank_link_sender_busy(&link.tx));
	zassert_ok(tank_link_sender_poll(&link.tx, TIMEOUT_MS));
	pump();
	zassert_equal(link.passed_up, 1U, "resent record passed up twice");
	zassert_equal(link.confirmed, 1U);
	zassert_equal(tank_link_receiver_stats(&rx)->duplicates, 1U);
}

ZTEST(link_delivery, test_duplicated_record_is_passed_up_once)
{
	link.dup_records = 1U;
	zassert_ok(tank_link_sender_send(&link.tx, data_a, sizeof(data_a), 0U));
	pump();
	zassert_equal(link.passed_up, 1U);
	zassert_equal(link.confirmed, 1U);
	zassert_equal(tank_link_sender_stats(&link.tx)->stale_acks, 1U, "second ack is stale");
}

ZTEST(link_delivery, test_give_up_then_next_record_gets_through)
{
	uint32_t now = 0U;

	link.drop_records = ATTEMPTS;
	zassert_ok(tank_link_sender_send(&link.tx, data_a, sizeof(data_a), now));
	for (unsigned int i = 1U; i < ATTEMPTS; i++) {
		now += TIMEOUT_MS;
		zassert_ok(tank_link_sender_poll(&link.tx, now));
	}
	now += TIMEOUT_MS;
	zassert_equal(tank_link_sender_poll(&link.tx, now), -ETIMEDOUT);
	zassert_ok(tank_link_sender_send(&link.tx, data_a, sizeof(data_a), now));
	pump();
	zassert_equal(link.passed_up, 1U);
	zassert_equal(link.confirmed, 1U);
}

ZTEST(link_delivery, test_frdm_reboot_restarting_seq_is_not_a_duplicate)
{
	const struct tank_link_sender_config cfg = tank_link_sender_default_config();

	zassert_ok(tank_link_sender_send(&link.tx, data_a, sizeof(data_a), 0U));
	pump();
	zassert_ok(tank_link_sender_init(&link.tx, &cfg, wire_write, NULL));
	zassert_ok(tank_link_sender_send(&link.tx, data_b, sizeof(data_b), 0U));
	pump();
	zassert_equal(link.passed_up, 2U);
	zassert_equal(link.confirmed, 2U);
}

ZTEST(link_delivery, test_both_sides_keep_working_across_seq_wrap)
{
	for (uint32_t i = 0U; i <= SEQ_WRAP; i++) {
		zassert_ok(tank_link_sender_send(&link.tx, data_a, sizeof(data_a), 0U));
		pump();
	}
	zassert_equal(link.passed_up, SEQ_WRAP + 1U);
	zassert_equal(link.confirmed, SEQ_WRAP + 1U);
}
