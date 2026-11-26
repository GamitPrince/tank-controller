/*
 * Build the one-second scan record from the readings (S-058, P1-12).
 *
 * The scan thread (S-059) calls this once a second. It reads the current
 * status of every input and turns it into the record's scaled integer,
 * quality and age (interfaces/records.cddl, interfaces/signals-v1.yaml):
 *   - a 4-20 mA loop current in microamps (scale 0.001 mA);
 *   - a PT100 temperature in centi-degrees Celsius (scale 0.01 degC);
 *   - a digital contact as 1 when it is asserted (the signal's
 *     value_true_means holds) and 0 when it is clear.
 * A fault or unconfigured reading carries no value. A contact whose state has
 * never survived its debounce is a fault, because an unknown safety or alarm
 * contact must never read as healthy. A confirmed contact that is no longer
 * refreshed is stale and keeps its last value.
 *
 * Read only: it reads the inputs' state and changes nothing, so the
 * safety-chain reads in firmware/src/safety/ stay status-only.
 */

#ifndef TANK_RECORD_SCAN_BUILDER_H_
#define TANK_RECORD_SCAN_BUILDER_H_

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "boot_time.h"
#include "level_switch.h"
#include "loop_level.h"
#include "product_temperature.h"
#include "scan_codec.h"

/*
 * The inputs one scan reports, in the order they appear in it: loop levels,
 * then temperatures, then digital contacts. The arrays must stay the same
 * from scan to scan so consecutive scans can be delta encoded.
 */
struct tank_scan_sources {
	const struct tank_loop_level *levels;
	size_t level_count;
	const struct tank_product_temperature *temperatures;
	size_t temperature_count;
	/* Safety-chain, alarm and equipment status contacts alike. */
	const struct tank_level_switch *contacts;
	size_t contact_count;
};

/*
 * Fill out with the scan taken at up_ms: the boot id and time from bt, the
 * signal list version sl, the scan's seq, and one reading per input. Returns
 * 0; -EINVAL if an argument is NULL, an array with a count is NULL, there are
 * no inputs or more than TANK_SCAN_MAX_READINGS, or bt is not initialised.
 * On error out is not a valid scan.
 */
int tank_scan_build(const struct tank_scan_sources *src, const struct tank_boot_time *bt,
		    uint32_t sl, uint32_t seq, uint32_t up_ms, struct tank_scan *out);

/*
 * True when s should go out at once instead of waiting for its batch (S-065,
 * NFR-01): it differs from prev in any reading's quality or in whether it
 * carries a value, or in the value of one of its last contact_count readings,
 * the contacts, which the builder puts last. Analogue values, which move every
 * scan, do not count. Scans that do not line up (another count or id), or a
 * contact_count above the scan's count, count as changed; a NULL scan never
 * does.
 */
bool tank_scan_prompt_change(const struct tank_scan *prev, const struct tank_scan *s,
			     size_t contact_count);

#endif /* TANK_RECORD_SCAN_BUILDER_H_ */
