/*
 * Unity tests for the ESP32 publisher (S-064): each RECORD the FRDM sends is
 * published unchanged as one MQTT message on tank/{device_id}/records, and its
 * DELIVERED goes back only when that message's PUBACK arrives. A failed
 * publish, a stale PUBACK and a record the FRDM gave up on confirm nothing.
 */

#include <errno.h>
#include <string.h>
#include <unity.h>

#include "link_endpoint.h"
#include "link_frame.h"
#include "publisher.h"

#define FRAME_BYTES_MAX (TANK_LINK_FRAME_MAX + 1U)
#define DEV_ID "0123456789abcdef0123456789abcdef"
#define TOPIC "tank/" DEV_ID "/records"
#define SEQ_A 7U
#define SEQ_B 8U
#define MSG_ID_FIRST 41
#define NOT_CONNECTED (-1)

/* A batch of two records, as the FRDM sends it: a CBOR array head first. */
static const uint8_t batch_a[] = {0x82U, 0xA1U, 0x01U, 0xA1U, 0x02U};
static const uint8_t batch_b[] = {0x81U, 0xA1U, 0x03U};

static struct tank_link_endpoint ep;
static struct tank_publisher pub;

/* What the broker and the UART saw. */
static struct {
	int next_msg_id;
	int publish_result;
	unsigned int publishes;
	char topic[TANK_PUBLISHER_TOPIC_MAX];
	uint8_t payload[TANK_LINK_PAYLOAD_MAX];
	size_t payload_len;
	unsigned int delivered;
	uint16_t delivered_seq;
} seen;

static int fake_publish(void *ctx, const char *topic, const uint8_t *payload, size_t len)
{
	(void)ctx;
	seen.publishes++;
	if (seen.publish_result != 0) {
		return seen.publish_result;
	}
	strcpy(seen.topic, topic);
	memcpy(seen.payload, payload, len);
	seen.payload_len = len;
	return seen.next_msg_id++;
}

/* The UART to the FRDM: decode each frame the endpoint writes. */
static int fake_uart_write(void *ctx, const uint8_t *bytes, size_t len)
{
	struct tank_link_decoder dec;
	struct tank_link_msg msg;

	(void)ctx;
	tank_link_decoder_init(&dec);
	for (size_t i = 0U; i < len; i++) {
		if (tank_link_decoder_push(&dec, bytes[i], &msg) == TANK_LINK_RX_FRAME) {
			TEST_ASSERT_EQUAL_INT(TANK_LINK_DELIVERED, msg.type);
			TEST_ASSERT_EQUAL_size_t(TANK_LINK_DELIVERED_PAYLOAD_LEN, msg.payload_len);
			seen.delivered++;
			/* The confirmed seq is the payload, low byte first (S-042). */
			seen.delivered_seq =
			    (uint16_t)(msg.payload[0] | ((uint16_t)msg.payload[1] << 8U));
		}
	}
	return 0;
}

static void frdm_sends(uint16_t seq, const uint8_t *payload, size_t len)
{
	const struct tank_link_msg msg = {
	    .type = TANK_LINK_RECORD, .seq = seq, .payload = payload, .payload_len = len};
	uint8_t frame[FRAME_BYTES_MAX];
	size_t frame_len = 0U;

	TEST_ASSERT_EQUAL_INT(0, tank_link_frame_encode(&msg, frame, sizeof(frame), &frame_len));
	for (size_t i = 0U; i < frame_len; i++) {
		TEST_ASSERT_EQUAL_INT(0, tank_link_endpoint_push(&ep, frame[i]));
	}
}

static struct tank_publisher_config config(const char *device_id)
{
	return (struct tank_publisher_config){
	    .device_id = device_id, .publish_fn = fake_publish, .endpoint = &ep};
}

void setUp(void)
{
	const struct tank_publisher_config cfg = config(DEV_ID);

	memset(&seen, 0, sizeof(seen));
	seen.next_msg_id = MSG_ID_FIRST;
	TEST_ASSERT_EQUAL_INT(
	    0, tank_link_endpoint_init(&ep, tank_publisher_on_record, fake_uart_write, &pub));
	TEST_ASSERT_EQUAL_INT(0, tank_publisher_init(&pub, &cfg));
}

void tearDown(void)
{
}

static void test_topic_is_built_from_the_device_id(void)
{
	TEST_ASSERT_EQUAL_STRING(TOPIC, tank_publisher_topic(&pub));
	TEST_ASSERT_NULL(tank_publisher_topic(NULL));
}

static void test_a_record_is_published_unchanged_and_confirmed_on_puback(void)
{
	frdm_sends(SEQ_A, batch_a, sizeof(batch_a));
	TEST_ASSERT_EQUAL_UINT(1U, seen.publishes);
	TEST_ASSERT_EQUAL_STRING(TOPIC, seen.topic);
	TEST_ASSERT_EQUAL_size_t(sizeof(batch_a), seen.payload_len);
	TEST_ASSERT_EQUAL_MEMORY(batch_a, seen.payload, sizeof(batch_a));
	TEST_ASSERT_EQUAL_UINT_MESSAGE(0U, seen.delivered, "no DELIVERED before the PUBACK");

	TEST_ASSERT_EQUAL_INT(0, tank_publisher_on_puback(&pub, MSG_ID_FIRST));
	TEST_ASSERT_EQUAL_UINT(1U, seen.delivered);
	TEST_ASSERT_EQUAL_UINT16(SEQ_A, seen.delivered_seq);
	TEST_ASSERT_EQUAL_UINT32(1U, tank_publisher_stats(&pub)->confirmed);
}

static void test_a_failed_publish_is_never_confirmed(void)
{
	seen.publish_result = NOT_CONNECTED;
	frdm_sends(SEQ_A, batch_a, sizeof(batch_a));
	TEST_ASSERT_EQUAL_UINT32(1U, tank_publisher_stats(&pub)->publish_errors);
	TEST_ASSERT_EQUAL_INT(NOT_CONNECTED, tank_publisher_stats(&pub)->last_error);
	TEST_ASSERT_EQUAL_INT(0, tank_publisher_on_puback(&pub, MSG_ID_FIRST));
	TEST_ASSERT_EQUAL_UINT(0U, seen.delivered);
	TEST_ASSERT_EQUAL_UINT32(1U, tank_publisher_stats(&pub)->stale_acks);
}

static void test_a_zero_message_id_counts_as_a_failed_publish(void)
{
	seen.next_msg_id = 0;
	frdm_sends(SEQ_A, batch_a, sizeof(batch_a));
	TEST_ASSERT_EQUAL_UINT32(1U, tank_publisher_stats(&pub)->publish_errors);
	TEST_ASSERT_EQUAL_INT(-EIO, tank_publisher_stats(&pub)->last_error);
}

static void test_a_puback_for_another_message_confirms_nothing(void)
{
	frdm_sends(SEQ_A, batch_a, sizeof(batch_a));
	TEST_ASSERT_EQUAL_INT(0, tank_publisher_on_puback(&pub, MSG_ID_FIRST + 1));
	TEST_ASSERT_EQUAL_UINT(0U, seen.delivered);
	TEST_ASSERT_EQUAL_UINT32(1U, tank_publisher_stats(&pub)->stale_acks);
	TEST_ASSERT_EQUAL_INT(0, tank_publisher_on_puback(&pub, MSG_ID_FIRST));
	TEST_ASSERT_EQUAL_UINT_MESSAGE(1U, seen.delivered, "the right PUBACK still confirms");
	TEST_ASSERT_EQUAL_INT(0, tank_publisher_on_puback(&pub, MSG_ID_FIRST));
	TEST_ASSERT_EQUAL_UINT_MESSAGE(1U, seen.delivered,
				       "a repeated PUBACK confirms nothing more");
}

static void test_a_new_record_replaces_the_one_the_frdm_gave_up_on(void)
{
	frdm_sends(SEQ_A, batch_a, sizeof(batch_a));
	frdm_sends(SEQ_B, batch_b, sizeof(batch_b));
	TEST_ASSERT_EQUAL_UINT(2U, seen.publishes);
	TEST_ASSERT_EQUAL_INT(0, tank_publisher_on_puback(&pub, MSG_ID_FIRST));
	TEST_ASSERT_EQUAL_UINT_MESSAGE(0U, seen.delivered, "the old PUBACK is stale");
	TEST_ASSERT_EQUAL_INT(0, tank_publisher_on_puback(&pub, MSG_ID_FIRST + 1));
	TEST_ASSERT_EQUAL_UINT(1U, seen.delivered);
	TEST_ASSERT_EQUAL_UINT16(SEQ_B, seen.delivered_seq);
}

static void test_bad_device_ids_and_arguments_are_refused(void)
{
	static const char *const bad_ids[] = {"", "tank/01", "a+b", "a#b",
					      "0123456789abcdef0123456789abcdef0"};
	struct tank_publisher_config cfg = config(DEV_ID);

	for (size_t i = 0U; i < sizeof(bad_ids) / sizeof(bad_ids[0]); i++) {
		cfg = config(bad_ids[i]);
		TEST_ASSERT_EQUAL_INT_MESSAGE(-EINVAL, tank_publisher_init(&pub, &cfg), bad_ids[i]);
	}
	cfg = config(NULL);
	TEST_ASSERT_EQUAL_INT(-EINVAL, tank_publisher_init(&pub, &cfg));
	cfg = config(DEV_ID);
	cfg.publish_fn = NULL;
	TEST_ASSERT_EQUAL_INT(-EINVAL, tank_publisher_init(&pub, &cfg));
	cfg = config(DEV_ID);
	cfg.endpoint = NULL;
	TEST_ASSERT_EQUAL_INT(-EINVAL, tank_publisher_init(&pub, &cfg));
	TEST_ASSERT_EQUAL_INT(-EINVAL, tank_publisher_init(NULL, &cfg));
	TEST_ASSERT_EQUAL_INT(-EINVAL, tank_publisher_init(&pub, NULL));
	TEST_ASSERT_EQUAL_INT(-EINVAL, tank_publisher_on_puback(NULL, MSG_ID_FIRST));
	TEST_ASSERT_NULL(tank_publisher_stats(NULL));
	tank_publisher_on_record(NULL, SEQ_A, batch_a, sizeof(batch_a));
	tank_publisher_on_record(&pub, SEQ_A, NULL, sizeof(batch_a));
	TEST_ASSERT_EQUAL_UINT(0U, seen.publishes);
}

int main(void)
{
	UNITY_BEGIN();
	RUN_TEST(test_topic_is_built_from_the_device_id);
	RUN_TEST(test_a_record_is_published_unchanged_and_confirmed_on_puback);
	RUN_TEST(test_a_failed_publish_is_never_confirmed);
	RUN_TEST(test_a_zero_message_id_counts_as_a_failed_publish);
	RUN_TEST(test_a_puback_for_another_message_confirms_nothing);
	RUN_TEST(test_a_new_record_replaces_the_one_the_frdm_gave_up_on);
	RUN_TEST(test_bad_device_ids_and_arguments_are_refused);
	return UNITY_END();
}
