/* PT100 Callendar-Van Dusen linearisation. See pt100.h. */

#include "pt100.h"

#include <errno.h>
#include <math.h>

/* IEC 60751 coefficients for a platinum RTD with alpha = 0.003851. */
#define TANK_PT100_COEFF_A 3.9083e-3f
#define TANK_PT100_COEFF_B -5.775e-7f

int tank_pt100_temperature(float resistance_ohms, float *out_degc)
{
	if ((out_degc == NULL) || !(resistance_ohms > 0.0f)) {
		return -EINVAL;
	}

	const float ratio = resistance_ohms / TANK_PT100_R0_OHMS;
	const float discriminant = (TANK_PT100_COEFF_A * TANK_PT100_COEFF_A) -
				   (4.0f * TANK_PT100_COEFF_B * (1.0f - ratio));

	if (discriminant < 0.0f) {
		return -ERANGE;
	}

	*out_degc = (-TANK_PT100_COEFF_A + sqrtf(discriminant)) / (2.0f * TANK_PT100_COEFF_B);

	return 0;
}
