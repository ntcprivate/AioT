#pragma once
#include <cstdint>
namespace tflite { namespace micro {
// Bundled common.cc single-rounding arithmetic, scoped only to our Conv adapter.
inline int32_t EcgSingleRoundMultiplier(int32_t x,int32_t multiplier,int shift) {
    const int total_shift=31-shift;
    return static_cast<int32_t>((static_cast<int64_t>(x)*multiplier+(int64_t{1}<<(total_shift-1)))>>total_shift);
}
inline int32_t EcgSingleRoundMultiplier(int64_t x,int32_t multiplier,int shift) {
    const int32_t reduced=multiplier<0x7fff0000?((multiplier+(1<<15))>>16):0x7fff;
    const int total_shift=15-shift;
    return static_cast<int32_t>((x*reduced+(int64_t{1}<<(total_shift-1)))>>total_shift);
}
} }
