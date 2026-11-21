/* Linear scaling for the measurement layer. See scaling.h. */

#include "scaling.h"

#include <errno.h>
#include <stddef.h>

static bool span_is_valid(float low, float high)
{
	return high > low;
}

int tank_scale_linear(float raw, float raw_low, float raw_high, float eng_low, float eng_high,
		      struct tank_scaled_reading *out)
{
	if (out == NULL) {
		return -EINVAL;
	}

	if (!span_is_valid(raw_low, raw_high) || !span_is_valid(eng_low, eng_high)) {
		return -EINVAL;
	}

	const float fraction = (raw - raw_low) / (raw_high - raw_low);

	out->value = eng_low + fraction * (eng_high - eng_low);
	out->in_range = (raw >= raw_low) && (raw <= raw_high);

	return 0;
}
