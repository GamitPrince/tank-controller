/*
 * A simulated FRDM-to-ESP32 UART link for the uplink tests (S-045). See
 * sim_link.h.
 */

#include "sim_link.h"

#include <errno.h>
#include <string.h>
#include <zephyr/ztest.h>

struct sim_link sim;

static struct tank_link_decoder esp_dec;
static struct tank_link_decoder frdm_dec;
static uint8_t reply[TANK_LINK_FRAME_MAX];
static size_t reply_len;
static uint8_t noise[TANK_LINK_FRAME_MAX];
static size_t noise_len;

void sim_link_reset(void)
{
	static const uint8_t status_payload[] = {0x00U};
	const struct tank_link_msg status = {
	    .type = TANK_LINK_LINK_STATUS,
	    .payload = status_payload,
	    .payload_len = sizeof(status_payload),
	};

	memset(&sim, 0, sizeof(sim));
	tank_link_receiver_init(&sim.rx);
	tank_link_decoder_init(&esp_dec);
	tank_link_decoder_init(&frdm_dec);
	reply_len = 0U;
	zassert_ok(tank_link_frame_encode(&status, noise, sizeof(noise), &noise_len));
}

static bool decode(struct tank_link_decoder *dec, const uint8_t *bytes, size_t len,
		   struct tank_link_msg *msg)
{
	enum tank_link_rx rx = TANK_LINK_RX_NEED_MORE;

	for (size_t i = 0U; i < len; i++) {
		rx = tank_link_decoder_push(dec, bytes[i], msg);
	}
	return rx == TANK_LINK_RX_FRAME;
}

static void log_record(const struct tank_link_msg *msg)
{
	if (sim.delivered < SIM_LOG_MAX) {
		sim.log_crc[sim.delivered] = tank_link_crc16(msg->payload, msg->payload_len);
		sim.log_len[sim.delivered] = msg->payload_len;
	}
	sim.delivered++;
	/* A batch's CBOR array header holds its record count (S-063). */
	sim.records += msg->payload[0] & 0x1FU;
}

int sim_link_write(void *ctx, const uint8_t *bytes, size_t len)
{
	struct tank_link_msg msg;
	int action;

	ARG_UNUSED(ctx);
	zassert_true(decode(&esp_dec, bytes, len, &msg), "the FRDM wrote a bad frame");
	if (sim.dead || (sim.dead_after != 0U && sim.delivered >= sim.dead_after)) {
		return 0;
	}
	if (sim.drop_records > 0U) {
		sim.drop_records--;
		return 0;
	}
	action = tank_link_receiver_on_msg(&sim.rx, &msg);
	if (action == TANK_LINK_RECV_DELIVER) {
		log_record(&msg);
	}
	if (action == TANK_LINK_RECV_NONE) {
		return 0;
	}
	zassert_ok(tank_link_receiver_confirm(&sim.rx, msg.seq, reply, sizeof(reply), &reply_len));
	if (sim.drop_delivered > 0U) {
		sim.drop_delivered--;
		reply_len = 0U;
	}
	return 0;
}

int sim_link_read(void *ctx, struct tank_link_msg *msg, uint32_t timeout_ms)
{
	int err = sim.read_error;

	ARG_UNUSED(ctx);
	if (err != 0) {
		sim.read_error = 0;
		return err;
	}
	if (reply_len > 0U) {
		zassert_true(decode(&frdm_dec, reply, reply_len, msg));
		reply_len = 0U;
		return 0;
	}
	if (sim.noise_every_ms != 0U && sim.noise_every_ms < timeout_ms) {
		sim.clock_ms += sim.noise_every_ms;
		zassert_true(decode(&frdm_dec, noise, noise_len, msg));
		return 0;
	}
	sim.clock_ms += timeout_ms;
	return -EAGAIN;
}

uint32_t sim_link_now(void *ctx)
{
	ARG_UNUSED(ctx);
	return sim.clock_ms;
}
