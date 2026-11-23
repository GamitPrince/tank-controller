/* MAX31865 register decode and fault classification. See max31865.h. */

#include "max31865.h"

#include <errno.h>

/* The RTD register's ADC code is 15 bits wide, bits 15:1 of the 16-bit register. */
#define TANK_MAX31865_ADC_CODE_BITS 15
#define TANK_MAX31865_ADC_CODE_SCALE ((float)(1U << TANK_MAX31865_ADC_CODE_BITS))

/*
 * An open circuit removes the RTD from the bridge, so the ADC saturates near
 * full scale; a short pulls it near zero. Neither threshold is the datasheet's
 * own fault comparator (that is the fault_flags byte); they are this module's
 * own margin for recognising the same conditions from the code alone, used
 * only when the fault byte does not already say so.
 */
#define TANK_MAX31865_OPEN_CODE_THRESHOLD 32000U
#define TANK_MAX31865_SHORT_CODE_THRESHOLD 16U

int tank_max31865_decode(uint8_t rtd_msb, uint8_t rtd_lsb, uint8_t fault_status, float rref_ohms,
			 struct tank_max31865_reading *out)
{
	if ((out == NULL) || !(rref_ohms > 0.0f)) {
		return -EINVAL;
	}

	const uint16_t raw = (uint16_t)((uint16_t)rtd_msb << 8) | rtd_lsb;
	const bool fault_bit = (raw & 0x1U) != 0U;
	const uint16_t code15 = raw >> 1;

	out->raw_code15 = code15;
	out->fault_bit = fault_bit;
	out->fault_flags = fault_status;
	out->resistance_ohms = ((float)code15 / TANK_MAX31865_ADC_CODE_SCALE) * rref_ohms;

	return 0;
}

bool tank_max31865_reading_is_open(const struct tank_max31865_reading *reading)
{
	if (reading == NULL) {
		return false;
	}

	const bool flagged_open =
	    (reading->fault_flags &
	     (TANK_MAX31865_FAULT_REFIN_LOW_OPEN | TANK_MAX31865_FAULT_RTDIN_LOW_OPEN)) != 0U;

	return flagged_open || (reading->raw_code15 >= TANK_MAX31865_OPEN_CODE_THRESHOLD);
}

bool tank_max31865_reading_is_short(const struct tank_max31865_reading *reading)
{
	if (reading == NULL) {
		return false;
	}

	if (tank_max31865_reading_is_open(reading)) {
		/* Full-scale and near-zero cannot both be true; open takes precedence. */
		return false;
	}

	return reading->raw_code15 <= TANK_MAX31865_SHORT_CODE_THRESHOLD;
}
