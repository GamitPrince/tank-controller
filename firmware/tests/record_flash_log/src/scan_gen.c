/*
 * Deterministic Phase 1 scans for the outage buffer tests (S-039).
 */

#include "scan_gen.h"

#include <string.h>

#include <zephyr/drivers/flash.h>
#include <zephyr/ztest.h>

#define LOG_OFFSET 0x200000U
#define LOG_REGION (8U * 1024U * 1024U)
#define SECTOR_SIZE 4096U
#define FULL_INTERVAL 60U
#define ACK_PERSIST 1U
#define ANALOGUE_SIGNALS 8U
#define MID_SCALE 12000
#define NOISE_SPAN 7U
#define NOISE_OFFSET 3
#define TOGGLE_PERIOD 3600U
#define FAULT_FIRST 2000U
#define FAULT_LAST 2100U
#define FAULT_QUALITY 3U
#define EPOCH_AT_SYNC 1795000000U
#define MS_PER_SCAN 1000U

static const struct device *const flash_dev = DEVICE_DT_GET(DT_CHOSEN(zephyr_flash_controller));

static int32_t noise(uint32_t seq, uint8_t i)
{
	uint32_t h = (seq * 2654435761U) ^ ((uint32_t)i * 40503U);

	return (int32_t)((h >> 16) % NOISE_SPAN) - NOISE_OFFSET;
}

static void make_reading(struct tank_scan_reading *rd, uint32_t seq, uint8_t i)
{
	rd->id = (uint16_t)(1001U + i);
	rd->has_val = true;
	rd->q = 0U;
	rd->age_ms = 20U + i;
	if (i >= ANALOGUE_SIGNALS) {
		rd->val = (int32_t)((seq / TOGGLE_PERIOD + i) % 2U);
	} else if (i == 1U && seq >= FAULT_FIRST && seq < FAULT_LAST) {
		rd->has_val = false;
		rd->val = 0;
		rd->q = FAULT_QUALITY;
	} else {
		rd->val = MID_SCALE + noise(seq, i);
	}
}

void scan_gen(struct tank_scan *s, uint8_t boot, uint32_t seq, bool sync)
{
	memset(s, 0, sizeof(*s));
	memset(s->boot_id, 0xB0 + boot, TANK_BOOT_ID_LEN);
	s->sl = 1U;
	s->seq = seq;
	s->up_ms = seq * MS_PER_SCAN;
	s->tk = sync && seq >= GEN_SYNC_SEQ;
	s->t_s = s->tk ? EPOCH_AT_SYNC + seq : 0U;
	s->count = GEN_SIGNALS;
	for (uint8_t i = 0U; i < GEN_SIGNALS; i++) {
		make_reading(&s->r[i], seq, i);
	}
}

void scan_gen_check(const struct tank_log_item *item, uint8_t boot, uint32_t seq, bool sync)
{
	struct tank_scan want;

	scan_gen(&want, boot, seq, sync);
	zassert_equal(item->kind, TANK_LOG_ITEM_SCAN);
	zassert_equal(item->scan.seq, seq, "got seq %u want %u", item->scan.seq, seq);
	zassert_mem_equal(&item->scan, &want, sizeof(want), "scan %u differs", seq);
}

struct tank_flash_log_config scan_gen_log_config(size_t sectors)
{
	return (struct tank_flash_log_config){
	    .flash = flash_dev,
	    .offset = LOG_OFFSET,
	    .size = sectors * SECTOR_SIZE,
	    .sector_size = SECTOR_SIZE,
	    .full_interval = FULL_INTERVAL,
	    .ack_persist_interval = ACK_PERSIST,
	};
}

void scan_gen_erase(void)
{
	zassert_true(device_is_ready(flash_dev));
	zassert_ok(flash_erase(flash_dev, LOG_OFFSET, LOG_REGION));
}
