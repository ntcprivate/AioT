// Digital diagnostic fixtures only; not ECG, lead detection hardware or AI validation.
#include "lead_off.h"
#include <cassert>
#include <cstdio>

int main() {
    static_assert(ad8232::kLoPlusGpio == 27 && ad8232::kLoMinusGpio == 26);
    for (unsigned state = 0; state < 4; ++state) {
        const uint8_t p = state & 1, m = (state >> 1) & 1;
        assert(ad8232::lead_off(p,m) == (state != 0));
        assert(ad8232::lead_off(p,m) == ad8232::lead_off(m,p));
        ad8232::LeadDiagnostics d = {};
        for (unsigned i = 0; i < 256; ++i) d.observe(p,m);
        const unsigned any = state ? 256 : 0;
        assert(d.valid(any,256));
        assert(d.plus_high == 256*p && d.minus_high == 256*m);
        assert(d.both_high == (state == 3 ? 256u : 0u));
        assert(d.plus_raw == p && d.minus_raw == m);
    }
    // Every possible 8-sample combination; independent OR count and snapshot copy.
    for (unsigned sequence = 0; sequence < 65536; ++sequence) {
        ad8232::LeadDiagnostics d = {};
        unsigned any = 0, swapped_any = 0;
        for (unsigned i = 0; i < 8; ++i) {
            const uint8_t p = (sequence >> (2*i)) & 1, m = (sequence >> (2*i+1)) & 1;
            d.observe(p,m); any += p || m;
            swapped_any += ad8232::lead_off(m,p);
        }
        assert(d.valid(any,8) && any == swapped_any);
        const auto frozen = d;
        d.observe(1,1); // Always changes counts, including an all-zero sequence.
        assert(frozen.valid(any,8) && !frozen.equals(d));
        auto corrupt = frozen; ++corrupt.plus_high;
        assert(!corrupt.valid(any,8));
    }
    ad8232::LeadDiagnostics alternating = {};
    for (unsigned i = 0; i < 256; ++i) alternating.observe(i%2, (i+1)%2);
    assert(alternating.valid(256,256));
    assert(alternating.plus_high == 128 && alternating.minus_high == 128 && !alternating.both_high);
    auto corrupt = alternating; corrupt.plus_raw = 2; assert(!corrupt.valid(256,256));
    puts("PASS: mapping27/26; active-HIGH truth table; 65536 sequences; OR swap invariant; immutable snapshots; corrupt counts/raw rejected; alternating leads can yield lo_any=256.");
}
