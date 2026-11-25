/*
 * Tests for the FRDM-to-ESP32 UART link frames (S-042).
 */

#include <errno.h>
#include <string.h>
#include <zephyr/ztest.h>

#include "link_frame.h"

#define FILL 0xAAU
#define SMALL_BODY_MAX 200U

static struct tank_link_decoder dec;
static uint8_t frame[TANK_LINK_FRAME_MAX];
static uint8_t payload[TANK_LINK_PAYLOAD_MAX];

/* Plain COBS for hand-built bodies under 254 bytes. */
static size_t cobs_wrap(const uint8_t *body, size_t len, uint8_t *out)
{
	size_t code_idx = 0U;
	size_t o = 1U;
	uint8_t code = 1U;

	for (size_t i = 0; i < len; i++) {
		if (body[i] == 0U) {
			out[code_idx] = code;
			code_idx = o++;
			code = 1U;
		} else {
			out[o++] = body[i];
			code++;
		}
	}
	out[code_idx] = code;
	out[o++] = 0U;
	return o;
}

/* Body with a correct CRC appended; returns its length. */
static size_t make_body(uint8_t version, uint8_t type, uint8_t *body)
{
	const uint8_t header[] = {version, type, 0x34U, 0x12U, 0x55U};
	uint16_t crc;

	memcpy(body, header, sizeof(header));
	crc = tank_link_crc16(body, sizeof(header));
	body[sizeof(header)] = (uint8_t)(crc & 0xFFU);
	body[sizeof(header) + 1U] = (uint8_t)(crc >> 8);
	return sizeof(header) + 2U;
}

/* Push bytes; returns the last non-NEED_MORE result and counts frames. */
static enum tank_link_rx push_all(const uint8_t *bytes, size_t len, struct tank_link_msg *msg,
				  unsigned int *frames)
{
	enum tank_link_rx last = TANK_LINK_RX_NEED_MORE;

	*frames = 0U;
	for (size_t i = 0; i < len; i++) {
		enum tank_link_rx r = tank_link_decoder_push(&dec, bytes[i], msg);

		if (r == TANK_LINK_RX_FRAME) {
			(*frames)++;
		}
		if (r != TANK_LINK_RX_NEED_MORE) {
			last = r;
		}
	}
	return last;
}

static size_t encode(uint8_t type, uint16_t seq, size_t len)
{
	const struct tank_link_msg msg = {
	    .type = type, .seq = seq, .payload = payload, .payload_len = len};
	size_t out_len = 0U;

	zassert_ok(tank_link_frame_encode(&msg, frame, sizeof(frame), &out_len));
	return out_len;
}

static void assert_good_frame_decodes(void)
{
	struct tank_link_msg msg;
	unsigned int frames;
	const size_t len = encode(TANK_LINK_RECORD, 7U, 3U);

	zassert_equal(push_all(frame, len, &msg, &frames), TANK_LINK_RX_FRAME);
	zassert_equal(frames, 1U);
	zassert_equal(msg.seq, 7U);
}

static void before(void *fixture)
{
	ARG_UNUSED(fixture);
	tank_link_decoder_init(&dec);
	for (size_t i = 0; i < sizeof(payload); i++) {
		payload[i] = (i % 3U == 0U) ? 0U : (uint8_t)i;
	}
}

ZTEST(link_frame, test_crc_known_answer)
{
	zassert_equal(tank_link_crc16((const uint8_t *)"123456789", 9U), 0x29B1U);
}

ZTEST(link_frame, test_cobs_known_answer)
{
	static const uint8_t expected[] = {0x03, 0x01, 0x01, 0x03, 0x01, 0x11,
					   0x04, 0x22, 0xC8, 0x0A, 0x00};

	payload[0] = 0x11U;
	payload[1] = 0x00U;
	payload[2] = 0x22U;
	zassert_equal(encode(TANK_LINK_RECORD, 0x0100U, 3U), sizeof(expected));
	zassert_mem_equal(frame, expected, sizeof(expected));
}

static void check_round_trip(uint8_t type, size_t len)
{
	struct tank_link_msg msg;
	unsigned int frames;
	const size_t out_len = encode(type, 0xBEEFU, len);

	zassert_true(out_len <= TANK_LINK_FRAME_MAX);
	zassert_is_null(memchr(frame, 0, out_len - 1U), "zero inside frame");
	zassert_equal(frame[out_len - 1U], 0U);
	zassert_equal(push_all(frame, out_len, &msg, &frames), TANK_LINK_RX_FRAME);
	zassert_equal(msg.type, type);
	zassert_equal(msg.seq, 0xBEEFU);
	zassert_equal(msg.payload_len, len);
	zassert_mem_equal(msg.payload, payload, len);
}

ZTEST(link_frame, test_round_trip_every_type_and_size)
{
	static const size_t sizes[] = {0U, 1U, 2U, 253U, 254U, 255U, 508U, TANK_LINK_PAYLOAD_MAX};

	for (uint8_t type = TANK_LINK_RECORD; type <= TANK_LINK_TIME; type++) {
		for (size_t i = 0; i < ARRAY_SIZE(sizes); i++) {
			check_round_trip(type, sizes[i]);
		}
	}
}

ZTEST(link_frame, test_round_trip_all_zero_and_no_zero_payloads)
{
	memset(payload, 0, sizeof(payload));
	check_round_trip(TANK_LINK_RECORD, TANK_LINK_PAYLOAD_MAX);
	memset(payload, 0xFF, sizeof(payload));
	check_round_trip(TANK_LINK_RECORD, TANK_LINK_PAYLOAD_MAX);
}

ZTEST(link_frame, test_every_single_bit_flip_is_rejected)
{
	static uint8_t flipped[TANK_LINK_FRAME_MAX + 1U];
	const size_t len = encode(TANK_LINK_DELIVERED, 0x0203U, 40U);
	struct tank_link_msg msg;
	unsigned int frames;

	for (size_t byte = 0; byte < len; byte++) {
		for (unsigned int bit = 0; bit < 8U; bit++) {
			memcpy(flipped, frame, len);
			flipped[byte] ^= (uint8_t)(1U << bit);
			flipped[len] = 0U;
			tank_link_decoder_init(&dec);
			(void)push_all(flipped, len + 1U, &msg, &frames);
			zassert_equal(frames, 0U, "flip at byte %zu bit %u delivered", byte, bit);
		}
	}
}

ZTEST(link_frame, test_truncated_frame_rejected_then_resync)
{
	struct tank_link_msg msg;
	unsigned int frames;
	const size_t len = encode(TANK_LINK_RECORD, 1U, 20U);

	/* Lose five bytes from the middle of the frame. */
	memmove(&frame[5], &frame[10], len - 10U);
	zassert_true(push_all(frame, len - 5U, &msg, &frames) < 0);
	zassert_equal(frames, 0U);
	assert_good_frame_decodes();
}

ZTEST(link_frame, test_too_short)
{
	static const uint8_t raw[] = {0x06, 0x01, 0x01, 0x02, 0x03, 0x04, 0x00};
	struct tank_link_msg msg;
	unsigned int frames;

	zassert_equal(push_all(raw, sizeof(raw), &msg, &frames), TANK_LINK_RX_TOO_SHORT);
	assert_good_frame_decodes();
}

ZTEST(link_frame, test_overrun_is_too_long_then_resync)
{
	struct tank_link_msg msg;

	for (size_t i = 0; i < TANK_LINK_FRAME_MAX + 10U; i++) {
		zassert_equal(tank_link_decoder_push(&dec, 0x42U, &msg), TANK_LINK_RX_NEED_MORE);
	}
	zassert_equal(tank_link_decoder_push(&dec, 0U, &msg), TANK_LINK_RX_TOO_LONG);
	assert_good_frame_decodes();
}

ZTEST(link_frame, test_body_longer_than_max_is_too_long)
{
	struct tank_link_msg msg;

	/* Each 0x01 code decodes to a zero: fits the raw buffer, not the body. */
	for (size_t i = 0; i < sizeof(dec.raw); i++) {
		(void)tank_link_decoder_push(&dec, 0x01U, &msg);
	}
	zassert_equal(tank_link_decoder_push(&dec, 0U, &msg), TANK_LINK_RX_TOO_LONG);
}

ZTEST(link_frame, test_bad_cobs)
{
	static const uint8_t raw[] = {0x05, 0x01, 0x00};
	struct tank_link_msg msg;
	unsigned int frames;

	zassert_equal(push_all(raw, sizeof(raw), &msg, &frames), TANK_LINK_RX_BAD_COBS);
}

ZTEST(link_frame, test_bad_version_and_bad_type)
{
	uint8_t body[SMALL_BODY_MAX];
	uint8_t raw[SMALL_BODY_MAX];
	struct tank_link_msg msg;
	unsigned int frames;
	size_t len;

	len = cobs_wrap(body, make_body(2U, TANK_LINK_RECORD, body), raw);
	zassert_equal(push_all(raw, len, &msg, &frames), TANK_LINK_RX_BAD_VERSION);
	len = cobs_wrap(body, make_body(TANK_LINK_VERSION, 0x05U, body), raw);
	zassert_equal(push_all(raw, len, &msg, &frames), TANK_LINK_RX_BAD_TYPE);
	len = cobs_wrap(body, make_body(TANK_LINK_VERSION, 0x00U, body), raw);
	zassert_equal(push_all(raw, len, &msg, &frames), TANK_LINK_RX_BAD_TYPE);
	len = cobs_wrap(body, make_body(TANK_LINK_VERSION, TANK_LINK_TIME, body), raw);
	zassert_equal(push_all(raw, len, &msg, &frames), TANK_LINK_RX_FRAME);
	zassert_equal(msg.seq, 0x1234U);
	zassert_equal(msg.payload_len, 1U);
}

ZTEST(link_frame, test_mid_stream_start_and_back_to_back)
{
	static uint8_t stream[3U * 64U];
	struct tank_link_msg msg;
	unsigned int frames;
	size_t len = encode(TANK_LINK_RECORD, 1U, 30U);
	size_t n = len / 2U;

	/* Join mid-frame: only the second half of the first frame arrives. */
	memcpy(stream, &frame[len - n], n);
	memcpy(&stream[n], frame, len);
	n += len;
	stream[n++] = 0U; /* an idle delimiter is ignored */
	memcpy(&stream[n], frame, len);
	n += len;
	(void)push_all(stream, n, &msg, &frames);
	zassert_equal(frames, 2U);
	zassert_equal(dec.accepted, 2U);
	zassert_equal(dec.rejected, 1U);
}

ZTEST(link_frame, test_small_output_buffer_never_overrun)
{
	static uint8_t out[TANK_LINK_FRAME_MAX];
	const struct tank_link_msg msg = {
	    .type = TANK_LINK_RECORD, .seq = 9U, .payload = payload, .payload_len = 300U};
	const size_t needed = encode(TANK_LINK_RECORD, 9U, 300U);
	size_t out_len;

	for (size_t cap = 0; cap < needed; cap++) {
		memset(out, FILL, sizeof(out));
		zassert_equal(tank_link_frame_encode(&msg, out, cap, &out_len), -ENOSPC);
		for (size_t i = cap; i < sizeof(out); i++) {
			zassert_equal(out[i], FILL, "wrote past cap %zu", cap);
		}
	}
	zassert_ok(tank_link_frame_encode(&msg, out, needed, &out_len));
	zassert_equal(out_len, needed);
}

ZTEST(link_frame, test_encode_rejects_bad_arguments)
{
	struct tank_link_msg msg = {.type = 0U, .seq = 0U, .payload = payload, .payload_len = 1U};
	size_t out_len;

	zassert_equal(tank_link_frame_encode(&msg, frame, sizeof(frame), &out_len), -EINVAL);
	msg.type = TANK_LINK_TIME + 1U;
	zassert_equal(tank_link_frame_encode(&msg, frame, sizeof(frame), &out_len), -EINVAL);
	msg.type = TANK_LINK_RECORD;
	msg.payload_len = TANK_LINK_PAYLOAD_MAX + 1U;
	zassert_equal(tank_link_frame_encode(&msg, frame, sizeof(frame), &out_len), -EINVAL);
	msg.payload = NULL;
	msg.payload_len = 1U;
	zassert_equal(tank_link_frame_encode(&msg, frame, sizeof(frame), &out_len), -EINVAL);
	msg.payload_len = 0U;
	zassert_ok(tank_link_frame_encode(&msg, frame, sizeof(frame), &out_len));
	zassert_equal(tank_link_frame_encode(NULL, frame, sizeof(frame), &out_len), -EINVAL);
	zassert_equal(tank_link_frame_encode(&msg, NULL, sizeof(frame), &out_len), -EINVAL);
	zassert_equal(tank_link_frame_encode(&msg, frame, sizeof(frame), NULL), -EINVAL);
}

ZTEST_SUITE(link_frame, NULL, NULL, before, NULL, NULL);
