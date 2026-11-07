#pragma once
#include <cstdint>

namespace ad8232 {
// Physical wiring for this integrated project. These are driven digital
// outputs from the module, not the electrode analog input terminals.
constexpr int kLoPlusGpio = 27;
constexpr int kLoMinusGpio = 26;
constexpr bool lead_off(uint8_t plus, uint8_t minus) {
    return plus != 0 || minus != 0; // AD8232 LOD outputs are active HIGH.
}

// Queued with the immutable ADC summary, never read from live GPIO by logger.
struct LeadDiagnostics {
    uint32_t plus_high, minus_high, both_high;
    uint8_t plus_raw, minus_raw; // Last sample of the completed block.

    void observe(uint8_t plus, uint8_t minus) {
        plus_raw = plus; minus_raw = minus;
        plus_high += plus != 0;
        minus_high += minus != 0;
        both_high += plus != 0 && minus != 0;
    }
    bool valid(uint32_t any, uint32_t samples) const {
        if (plus_raw > 1 || minus_raw > 1 || plus_high > samples || minus_high > samples ||
            both_high > plus_high || both_high > minus_high || any > samples ||
            plus_high + minus_high - both_high != any) return false;
        if (!samples) return !plus_raw && !minus_raw;
        return (plus_raw ? plus_high > 0 : plus_high < samples) &&
               (minus_raw ? minus_high > 0 : minus_high < samples);
    }
    bool equals(const LeadDiagnostics& other) const {
        return plus_high == other.plus_high && minus_high == other.minus_high &&
               both_high == other.both_high && plus_raw == other.plus_raw && minus_raw == other.minus_raw;
    }
};
} // namespace ad8232
