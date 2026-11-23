/*
 * MAX31865 RTD-to-digital converter: register decode and fault classification.
 *
 * Story S-032 (P1-06). ADR-0002: six 3-wire PT100s on one MAX31865, a separate
 * chip select per channel, common SCK, MOSI and MISO. ADR-0003: own small
 * hardware-layer module, simulated on native_sim rather than driven through a
 * real SPI transaction, the same split as the AD4111 module takes.
 *
 * This module only turns the chip's own registers into a resistance and a
 * fault classification; it does not touch SPI, GPIO or devicetree, and it does
 * not know which tank position a chip select belongs to. A caller supplies the
 * two RTD register bytes and the fault status byte exactly as the chip framed
 * them (or as a simulated chip frames them in a test), and the reference
 * resistor value for that channel.
 *
 * The RTD register is 16 bits: a 15-bit ADC code in bits 15:1 and a fault bit
 * in bit 0. The fault status register is only meaningful once that fault bit
 * is set; this module decodes it either way and leaves the caller to decide
 * whether to look at it.
 */

#ifndef TANK_HARDWARE_MAX31865_H_
#define TANK_HARDWARE_MAX31865_H_

#include <stdbool.h>
#include <stdint.h>

/*
 * Chip selects the board fits on the shared bus (ADR-0002: six 3-wire PT100s,
 * a separate chip select per channel with common SCK, MOSI and MISO). Which
 * tank position each one carries is the signal list's business, not this
 * module's.
 */
#define TANK_MAX31865_CHIP_SELECT_MIN 1U
#define TANK_MAX31865_CHIP_SELECT_MAX 6U

/*
 * Fault status register bits (MAX31865 datasheet D7..D2), kept as the chip
 * defines them rather than renamed, so a reader can check this module against
 * the datasheet directly. D1 and D0 are reserved and always read zero.
 */
enum tank_max31865_fault_bit {
	TANK_MAX31865_FAULT_RTD_HIGH_THRESHOLD = 1U << 7,
	TANK_MAX31865_FAULT_RTD_LOW_THRESHOLD = 1U << 6,
	TANK_MAX31865_FAULT_REFIN_HIGH = 1U << 5,
	TANK_MAX31865_FAULT_REFIN_LOW_OPEN = 1U << 4,
	TANK_MAX31865_FAULT_RTDIN_LOW_OPEN = 1U << 3,
	TANK_MAX31865_FAULT_OVER_UNDER_VOLTAGE = 1U << 2,
};

/* A decoded reading: the resistance the chip measured, and why it might not be trustworthy. */
struct tank_max31865_reading {
	/* Measured RTD resistance in ohms, valid only when fault_bit is false. */
	float resistance_ohms;
	/* The 15-bit ADC code the resistance was computed from, kept for the
	 * open/short checks below, which look at the code rather than the
	 * resistance so they do not depend on the channel's reference resistor.
	 */
	uint16_t raw_code15;
	/* The register's own fault bit (RTD register bit 0). */
	bool fault_bit;
	/* Fault status register, decoded as enum tank_max31865_fault_bit flags. */
	uint8_t fault_flags;
};

/*
 * Decode one channel's raw RTD register bytes and fault status byte.
 *
 * rtd_msb and rtd_lsb are the two bytes of the RTD register, most significant
 * byte first, exactly as read over SPI. fault_status is the fault status
 * register, read only when the fault bit is set; its value is ignored by this
 * function when the fault bit is clear, but still copied into out->fault_flags
 * so a caller never has to re-derive it.
 *
 * rref_ohms is the reference resistor fitted to this channel (ADR-0002: a
 * precision low-tempco resistor per channel); it must be positive.
 *
 * Returns 0 on success, or -EINVAL if out is NULL or rref_ohms is not
 * positive. On failure out is left untouched.
 */
int tank_max31865_decode(uint8_t rtd_msb, uint8_t rtd_lsb, uint8_t fault_status, float rref_ohms,
			 struct tank_max31865_reading *out);

/*
 * Whether a decoded reading indicates an open circuit: the RTD has stopped
 * conducting, which the chip reports through RTDIN- open or REFIN- open, and
 * which also shows up as an ADC code pinned at or near full scale.
 */
bool tank_max31865_reading_is_open(const struct tank_max31865_reading *reading);

/*
 * Whether a decoded reading indicates a short: an ADC code pinned at or near
 * zero, which an open-circuit fault flag does not explain.
 */
bool tank_max31865_reading_is_short(const struct tank_max31865_reading *reading);

#endif /* TANK_HARDWARE_MAX31865_H_ */
