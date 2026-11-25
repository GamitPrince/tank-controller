/*
 * Deterministic Phase 1 scans for the outage buffer tests (S-039).
 */

#ifndef TANK_TEST_SCAN_GEN_H_
#define TANK_TEST_SCAN_GEN_H_

#include <stdint.h>

#include "flash_log.h"

#define GEN_SIGNALS 23U

/* Real time first becomes known at this seq of a boot. */
#define GEN_SYNC_SEQ 1000U

/* boot selects one of two boot ids (a power cycle starts boot 1). seq starts
 * at 1 in each boot; up is one second per scan; tk becomes true at
 * GEN_SYNC_SEQ, or never when sync is false.
 */
void scan_gen(struct tank_scan *s, uint8_t boot, uint32_t seq, bool sync);

/* Assert that item is the scan scan_gen() makes for the same arguments. */
void scan_gen_check(const struct tank_log_item *item, uint8_t boot, uint32_t seq, bool sync);

/* A log over the given number of 4 KB sectors of the test flash region. */
struct tank_flash_log_config scan_gen_log_config(size_t sectors);

/* Erase the whole test flash region. */
void scan_gen_erase(void);

#endif /* TANK_TEST_SCAN_GEN_H_ */
