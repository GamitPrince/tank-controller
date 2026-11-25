/*
 * The real SNTP network call (S-038, P1-15).
 *
 * `[Confirm]` this is a thin wrapper over Zephyr's net stack, in the same
 * spirit as ADR-0006's exclusion of thin ESP32 network wrappers from its
 * unit-test gate: it cannot be exercised by ztest on native_sim without a
 * real network path to a real NTP server, which would make the test
 * flaky and non-deterministic. It is not referenced by any Twister test
 * here and so is not measured by the 80% gate either way; it needs bench
 * verification (like P1-25) once there is a real network stack to run it
 * against. ADR-0003 does not say this exclusion applies to FRDM firmware
 * the way ADR-0006 says it for the ESP32, so this is a firmware-level
 * choice for the tech lead to confirm, not a decided exception.
 *
 * tank_clock_sync.h is what everything else calls: it takes this function
 * (or a fake, in tests) as its injected sync_fn, so the retry policy and
 * the boot-time bookkeeping are fully tested without this file ever
 * running in CI.
 */

#ifndef TANK_COMMUNICATIONS_SNTP_CLIENT_H_
#define TANK_COMMUNICATIONS_SNTP_CLIENT_H_

#include <stdint.h>

/* Public NTP pool (tech lead, 2026-11-23): works at any client site without
 * needing that site's own time server configured.
 */
#define TANK_SNTP_DEFAULT_SERVER "pool.ntp.org"

/*
 * Query server for the current time, waiting up to timeout_ms.
 * On success writes the server's Unix time in milliseconds to *epoch_ms_out
 * and returns 0. On failure (unreachable, timed out) returns a negative
 * error code and leaves *epoch_ms_out untouched.
 */
int tank_sntp_sync(const char *server, uint32_t timeout_ms, uint64_t *epoch_ms_out);

#endif /* TANK_COMMUNICATIONS_SNTP_CLIENT_H_ */
