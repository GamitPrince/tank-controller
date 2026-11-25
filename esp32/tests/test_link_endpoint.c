/*
 * Unity tests for the ESP32 end of the UART link (S-047): records passed up
 * once, DELIVERED written only on confirm and again for a confirmed resend,
 * and bad frames counted and dropped with the stream resynchronising.
 */

#include <errno.h>
#include <string.h>
#include <unity.h>

#include "link_endpoint.h"
#include "link_frame.h"

#define FRAME_BYTES_MAX (TANK_LINK_FRAME_MAX + 1U)
#define WRITE_FAILS (-EIO)
#define SEQ_A 7U
#define SEQ_B 8U
#define BAD_VERSION (TANK_LINK_VERSION + 1U)
#define BAD_TYPE 0x09U
#define COBS_MAX_RUN 0xFFU
#define CRC_FLIP 0x0101U

static const uint8_t payload_a[] = {0xA1U, 0x00U, 0x02U, 0x03U};
static const uint8_t payload_b[] = {0xA1U, 0x05U};

static struct tank_link_endpoint ep;

/* What the upper layer and the UART saw. */
static struct {
	unsigned int records;
	uint16_t last_seq;
	uint8_t last_payload[TANK_LINK_PAYLOAD_MAX];
	size_t last_len;
	unsigned int writes;
	uint8_t written[FRAME_BYTES_MAX];
	size_t written_len;
	int write_result;
} seen;

static void on_record(void *ctx, uint16_t seq, const uint8_t *payload, size_t len)
{
	(void)ctx;
	seen.records++;
	seen.last_seq = seq;
	memcpy(seen.last_payload, payload, len);
	seen.last_len = len;
}

static int on_write(void *ctx, const uint8_t *bytes, size_t len)
{
	(void)ctx;
	if (seen.write_result != 0) {
		return seen.write_result;
	}
	seen.writes++;
	memcpy(seen.written, bytes, len);
	seen.written_len = len;
	return 0;
}

static size_t record_frame(uint16_t seq, const uint8_t *payload, size_t len, uint8_t *out)
{
	const struct tank_link_msg msg = {
	    .type = TANK_LINK_RECORD, .seq = seq, .payload = payload, .payload_len = len};
	size_t out_len = 0U;

	TEST_ASSERT_EQUAL_INT(0, tank_link_frame_encode(&msg, out, FRAME_BYTES_MAX, &out_len));
	return out_len;
}

static int push_all(const uint8_t *bytes, size_t len)
{
	int rc = 0;

	for (size_t i = 0U; i < len && rc == 0; i++) {
		rc = tank_link_endpoint_push(&ep, bytes[i]);
	}
	return rc;
}

static void push_record(uint16_t seq, const uint8_t *payload, size_t len)
{
	uint8_t frame[FRAME_BYTES_MAX];

	TEST_ASSERT_EQUAL_INT(0, push_all(frame, record_frame(seq, payload, len, frame)));
}

/* COBS-encode body and add the delimiter, so tests can craft bad frames. */
static size_t cobs_frame(const uint8_t *body, size_t len, uint8_t *out)
{
	size_t code_at = 0U;
	size_t o = 1U;
	uint8_t code = 1U;

	for (size_t i = 0U; i < len; i++) {
		if (body[i] != 0U) {
			out[o++] = body[i];
			code++;
		}
		if (body[i] == 0U || code == COBS_MAX_RUN) {
			out[code_at] = code;
			code_at = o++;
			code = 1U;
		}
	}
	out[code_at] = code;
	out[o++] = 0U;
	return o;
}

/* A frame with no payload, the given version and type, and a CRC that is
 * correct unless crc_flip is non-zero.
 */
static size_t crafted_frame(uint8_t version, uint8_t type, uint16_t crc_flip, uint8_t *out)
{
	uint8_t body[TANK_LINK_HEADER_LEN + TANK_LINK_CRC_LEN] = {version, type, 0U, 0U};
	uint16_t crc = tank_link_crc16(body, TANK_LINK_HEADER_LEN) ^ crc_flip;

	body[TANK_LINK_HEADER_LEN] = (uint8_t)(crc & 0xFFU);
	body[TANK_LINK_HEADER_LEN + 1U] = (uint8_t)(crc >> 8);
	return cobs_frame(body, sizeof(body), out);
}

static struct tank_link_msg last_written(void)
{
	static struct tank_link_decoder dec;
	struct tank_link_msg msg = {0};
	enum tank_link_rx rx = TANK_LINK_RX_NEED_MORE;

	tank_link_decoder_init(&dec);
	for (size_t i = 0U; i < seen.written_len; i++) {
		rx = tank_link_decoder_push(&dec, seen.written[i], &msg);
	}
	TEST_ASSERT_EQUAL_INT(TANK_LINK_RX_FRAME, rx);
	return msg;
}

void setUp(void)
{
	memset(&seen, 0, sizeof(seen));
	TEST_ASSERT_EQUAL_INT(0, tank_link_endpoint_init(&ep, on_record, on_write, NULL));
}

void tearDown(void)
{
}

static void test_init_rejects_null_arguments(void)
{
	TEST_ASSERT_EQUAL_INT(-EINVAL, tank_link_endpoint_init(NULL, on_record, on_write, NULL));
	TEST_ASSERT_EQUAL_INT(-EINVAL, tank_link_endpoint_init(&ep, NULL, on_write, NULL));
	TEST_ASSERT_EQUAL_INT(-EINVAL, tank_link_endpoint_init(&ep, on_record, NULL, NULL));
	TEST_ASSERT_EQUAL_INT(-EINVAL, tank_link_endpoint_push(NULL, 0U));
	TEST_ASSERT_EQUAL_INT(-EINVAL, tank_link_endpoint_confirm(NULL, 0U));
	TEST_ASSERT_NULL(tank_link_endpoint_stats(NULL));
}

static void test_record_split_across_pushes_is_passed_up_once(void)
{
	uint8_t frame[FRAME_BYTES_MAX];
	size_t len = record_frame(SEQ_A, payload_a, sizeof(payload_a), frame);

	TEST_ASSERT_EQUAL_INT(0, push_all(frame, len - 1U));
	TEST_ASSERT_EQUAL_UINT(0U, seen.records);
	TEST_ASSERT_EQUAL_INT(0, tank_link_endpoint_push(&ep, frame[len - 1U]));
	TEST_ASSERT_EQUAL_UINT(1U, seen.records);
	TEST_ASSERT_EQUAL_UINT16(SEQ_A, seen.last_seq);
	TEST_ASSERT_EQUAL_size_t(sizeof(payload_a), seen.last_len);
	TEST_ASSERT_EQUAL_UINT8_ARRAY(payload_a, seen.last_payload, sizeof(payload_a));
	TEST_ASSERT_EQUAL_UINT(0U, seen.writes);
}

static void test_confirm_writes_delivered_for_that_seq(void)
{
	struct tank_link_msg msg;

	push_record(SEQ_A, payload_a, sizeof(payload_a));
	TEST_ASSERT_EQUAL_INT(0, tank_link_endpoint_confirm(&ep, SEQ_A));
	msg = last_written();
	TEST_ASSERT_EQUAL_UINT8(TANK_LINK_DELIVERED, msg.type);
	TEST_ASSERT_EQUAL_size_t(TANK_LINK_DELIVERED_PAYLOAD_LEN, msg.payload_len);
	TEST_ASSERT_EQUAL_UINT8(SEQ_A, msg.payload[0]);
	TEST_ASSERT_EQUAL_UINT8(0U, msg.payload[1]);
	TEST_ASSERT_EQUAL_UINT32(1U, tank_link_endpoint_stats(&ep)->confirms_written);
}

static void test_confirmed_resend_gets_delivered_again_and_is_not_passed_up(void)
{
	push_record(SEQ_A, payload_a, sizeof(payload_a));
	TEST_ASSERT_EQUAL_INT(0, tank_link_endpoint_confirm(&ep, SEQ_A));
	push_record(SEQ_A, payload_a, sizeof(payload_a));
	TEST_ASSERT_EQUAL_UINT(1U, seen.records);
	TEST_ASSERT_EQUAL_UINT(2U, seen.writes);
	TEST_ASSERT_EQUAL_UINT8(TANK_LINK_DELIVERED, last_written().type);
	TEST_ASSERT_EQUAL_UINT32(1U, tank_link_endpoint_stats(&ep)->duplicates);
}

static void test_unconfirmed_resend_is_dropped_silently(void)
{
	push_record(SEQ_A, payload_a, sizeof(payload_a));
	push_record(SEQ_A, payload_a, sizeof(payload_a));
	TEST_ASSERT_EQUAL_UINT(1U, seen.records);
	TEST_ASSERT_EQUAL_UINT(0U, seen.writes);
	push_record(SEQ_B, payload_b, sizeof(payload_b));
	TEST_ASSERT_EQUAL_UINT(2U, seen.records);
	TEST_ASSERT_EQUAL_UINT16(SEQ_B, seen.last_seq);
}

static void test_confirm_rejects_any_other_seq(void)
{
	TEST_ASSERT_EQUAL_INT(-EINVAL, tank_link_endpoint_confirm(&ep, SEQ_A));
	push_record(SEQ_A, payload_a, sizeof(payload_a));
	TEST_ASSERT_EQUAL_INT(-EINVAL, tank_link_endpoint_confirm(&ep, SEQ_B));
	TEST_ASSERT_EQUAL_UINT(0U, seen.writes);
}

static void test_write_errors_are_returned(void)
{
	uint8_t frame[FRAME_BYTES_MAX];
	size_t len = record_frame(SEQ_A, payload_a, sizeof(payload_a), frame);

	push_record(SEQ_A, payload_a, sizeof(payload_a));
	seen.write_result = WRITE_FAILS;
	TEST_ASSERT_EQUAL_INT(WRITE_FAILS, tank_link_endpoint_confirm(&ep, SEQ_A));
	TEST_ASSERT_EQUAL_UINT32(0U, tank_link_endpoint_stats(&ep)->confirms_written);
	TEST_ASSERT_EQUAL_INT(WRITE_FAILS, push_all(frame, len));
	seen.write_result = 0;
	push_record(SEQ_A, payload_a, sizeof(payload_a));
	TEST_ASSERT_EQUAL_UINT_MESSAGE(1U, seen.writes, "the next resend is confirmed");
}

static void test_bad_frames_are_counted_and_the_stream_resyncs(void)
{
	uint8_t frame[FRAME_BYTES_MAX];
	const uint8_t bad_cobs[] = {0x05U, 0x01U, 0x00U};
	const uint8_t short_body[] = {TANK_LINK_VERSION, TANK_LINK_RECORD};
	const struct tank_link_endpoint_stats *st = tank_link_endpoint_stats(&ep);
	size_t len;

	len = crafted_frame(TANK_LINK_VERSION, TANK_LINK_RECORD, CRC_FLIP, frame);
	TEST_ASSERT_EQUAL_INT(0, push_all(frame, len));
	TEST_ASSERT_EQUAL_INT(0, push_all(bad_cobs, sizeof(bad_cobs)));
	TEST_ASSERT_EQUAL_INT(0,
			      push_all(frame, cobs_frame(short_body, sizeof(short_body), frame)));
	for (size_t i = 0U; i <= TANK_LINK_FRAME_MAX; i++) {
		TEST_ASSERT_EQUAL_INT(0, tank_link_endpoint_push(&ep, 0x01U));
	}
	TEST_ASSERT_EQUAL_INT(0, tank_link_endpoint_push(&ep, 0x00U));
	TEST_ASSERT_EQUAL_INT(
	    0, push_all(frame, crafted_frame(BAD_VERSION, TANK_LINK_RECORD, 0U, frame)));
	TEST_ASSERT_EQUAL_INT(
	    0, push_all(frame, crafted_frame(TANK_LINK_VERSION, BAD_TYPE, 0U, frame)));

	TEST_ASSERT_EQUAL_UINT32(1U, st->rejected[-TANK_LINK_RX_BAD_CRC - 1]);
	TEST_ASSERT_EQUAL_UINT32(1U, st->rejected[-TANK_LINK_RX_BAD_COBS - 1]);
	TEST_ASSERT_EQUAL_UINT32(1U, st->rejected[-TANK_LINK_RX_TOO_SHORT - 1]);
	TEST_ASSERT_EQUAL_UINT32(1U, st->rejected[-TANK_LINK_RX_TOO_LONG - 1]);
	TEST_ASSERT_EQUAL_UINT32(1U, st->rejected[-TANK_LINK_RX_BAD_VERSION - 1]);
	TEST_ASSERT_EQUAL_UINT32(1U, st->rejected[-TANK_LINK_RX_BAD_TYPE - 1]);
	TEST_ASSERT_EQUAL_UINT(0U, seen.records);

	push_record(SEQ_B, payload_b, sizeof(payload_b));
	TEST_ASSERT_EQUAL_UINT(1U, seen.records);
}

static void test_other_frame_types_are_ignored(void)
{
	uint8_t frame[FRAME_BYTES_MAX];

	TEST_ASSERT_EQUAL_INT(
	    0, push_all(frame, crafted_frame(TANK_LINK_VERSION, TANK_LINK_LINK_STATUS, 0U, frame)));
	TEST_ASSERT_EQUAL_UINT32(1U, tank_link_endpoint_stats(&ep)->ignored);
	TEST_ASSERT_EQUAL_UINT32(1U, tank_link_endpoint_stats(&ep)->frames);
	TEST_ASSERT_EQUAL_UINT(0U, seen.records);
}

int main(void)
{
	UNITY_BEGIN();
	RUN_TEST(test_init_rejects_null_arguments);
	RUN_TEST(test_record_split_across_pushes_is_passed_up_once);
	RUN_TEST(test_confirm_writes_delivered_for_that_seq);
	RUN_TEST(test_confirmed_resend_gets_delivered_again_and_is_not_passed_up);
	RUN_TEST(test_unconfirmed_resend_is_dropped_silently);
	RUN_TEST(test_confirm_rejects_any_other_seq);
	RUN_TEST(test_write_errors_are_returned);
	RUN_TEST(test_bad_frames_are_counted_and_the_stream_resyncs);
	RUN_TEST(test_other_frame_types_are_ignored);
	return UNITY_END();
}
