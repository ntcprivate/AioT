// Host functional tests. Synthetic pulses are timing fixtures, not clinical ECG labels.
#include "signal.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <vector>
int raw_at(int64_t sample) {return 1000+static_cast<int>(sample%2000);}
void append(BeatWindowBuffer& b,int64_t start,int64_t end) {
    for(auto i=start;i<=end;++i){const char* issue=nullptr;assert(b.append(raw_at(i),i,1234567+i*4000,issue));assert(!issue);}
}
void check(BeatWindowBuffer& b,int64_t center) {
    float beat[256];BeatWindowInfo w;const char* issue=nullptr;
    assert(b.pop_ready(beat,w,issue));assert(!issue);assert(w.center_sample==center);
    assert(w.center_timestamp==1234567+center*4000 && w.start_sample==center-128 && w.end_sample==center+127);
    for(int i=0;i<256;++i)assert(beat[i]==raw_at(center-128+i));
}
int main() {
    // Four overlapping windows, wrap on 256/512 boundaries, exact center timestamp/data.
    BeatWindowBuffer b;const char* issue=nullptr;
    append(b,0,511);
    for(int64_t c=500;c<=503;++c)assert(b.enqueue(c,issue));
    assert(b.pending_count()==4 && b.stats().high_water==4);
    assert(!b.enqueue(504,issue) && strcmp(issue,"PENDING_QUEUE_FULL")==0);
    assert(b.stats().dropped_full==1 && b.pending_count()==4);
    assert(!b.enqueue(503,issue) && strcmp(issue,"DUPLICATE_R_CENTER")==0);
    assert(!b.enqueue(502,issue) && strcmp(issue,"R_CENTER_OUT_OF_ORDER")==0);
    append(b,512,626);float untouched[256];for(float& x:untouched)x=-1;
    BeatWindowInfo w;assert(!b.pop_ready(untouched,w,issue) && !issue);
    for(int64_t c=500;c<=503;++c){append(b,c+127,c+127);check(b,c);}
    assert(!b.pop_ready(untouched,w,issue) && !issue);
    assert(b.stats().completed==4 && b.stats().duplicate==1 && b.stats().out_of_order==1);
    // Ring data that aged out cannot become a CNN window.
    BeatWindowBuffer stale;append(stale,0,500);assert(stale.enqueue(500,issue));append(stale,501,1000);
    assert(!stale.pop_ready(untouched,w,issue) && strcmp(issue,"BEAT_RING_HISTORY_UNAVAILABLE")==0);
    assert(stale.stats().overwritten==1);for(float x:untouched)assert(x==-1);
    // Timestamp gap rejects atomically; no partial output.
    BeatWindowBuffer gap;
    for(int64_t i=0;i<=727;++i)assert(gap.append(raw_at(i),i,1234567+i*4000+(i==650?4000:0),issue));
    assert(gap.enqueue(600,issue));assert(!gap.pop_ready(untouched,w,issue));
    assert(strcmp(issue,"BEAT_TIMING_GAP")==0 && gap.stats().timing_errors==1);
    for(float x:untouched)assert(x==-1);
    // Reset cancels pending without reusing old center/history. Refill with absolute indices.
    BeatWindowBuffer invalid;append(invalid,0,600);assert(invalid.enqueue(600,issue));invalid.reset();
    assert(invalid.pending_count()==0 && invalid.stats().dropped_reset==1);
    append(invalid,601,1000);assert(invalid.enqueue(1000,issue));append(invalid,1001,1127);check(invalid,1000);
    assert(!invalid.append(1,1130,0,issue) && strcmp(issue,"BEAT_SAMPLE_INDEX_GAP")==0);
    assert(!invalid.enqueue(2000,issue) && strcmp(issue,"R_CENTER_HISTORY_UNAVAILABLE")==0);
    // Detector integration: inverted/wide PVC-like pulses, short/variable RR and block edges.
    for(int sign : {-1,1}) {
        BeatDetector detector;std::vector<int> centers={511,600,700,800,1023,1200,1300};
        std::vector<int> found;float beat[256];
        for(int i=0;i<1500;++i) {
            int raw=2048;for(int c:centers)if(std::abs(i-c)<=10)raw+=sign*(500-std::abs(i-c)*45);
            if(detector.push(raw,i*4000,beat,issue)){found.push_back(int(detector.last_window().center_sample));assert(!issue);}
            assert(!issue);
        }
        assert(found==centers);const auto s=detector.stats();
        assert(s.windows.completed==centers.size() && s.windows.high_water==2 && !s.windows.dropped_full);
        assert(!s.no_peak_resets && s.warmup_samples==500);
    }
    // Full valid streaming at nominal250Hz for20 virtual minutes; no allocations in push().
    BeatDetector stream;unsigned emitted=0;float beat[256];
    for(int i=0;i<300000;++i) {
        const int raw=i>=600 && i%100==0?2548:2048;
        if(stream.push(raw,9876543210LL+i*4000LL,beat,issue)) {
            assert(!issue);const auto info=stream.last_window();
            assert(info.center_sample==600+emitted*100 && info.center_timestamp==9876543210LL+info.center_sample*4000);
            assert(beat[128]==2548);++emitted;
        }
        assert(!issue);
    }
    assert(emitted==2993 && stream.stats().windows.high_water==2);
    assert(stream.stats().windows.dropped_full==0 && stream.stats().windows.duplicate==0);
    // Safety-gated input: lead-off invalidates a whole block and explicitly cancels pending.
    BeatDetector safety;int block[256];int64_t timestamps[256];
    for(int i=0;i<650;++i){safety.push(i==600?2548:2048,i*4000,beat,issue);assert(!issue);}
    assert(safety.pending_count()==1);const auto next=safety.stats().samples;
    safety.reset();assert(safety.pending_count()==0 && safety.stats().windows.dropped_reset==1);
    for(int i=0;i<256;++i){block[i]=0;timestamps[i]=(650+i)*4000;}
    assert(strcmp(signal_block_reason(block,timestamps),"ADC_SATURATION")==0);
    for(int i=650;i<1250;++i){assert(!safety.push(2048,i*4000,beat,issue));assert(!issue);}
    assert(safety.stats().samples==next+600 && safety.stats().external_resets==1);
    puts("PASS: overlapping/variable-RR/polarity windows; FIFO full/order/duplicate/expiry; atomic gaps; reset/invalid cancellation;20min250Hz host stream.");
}
