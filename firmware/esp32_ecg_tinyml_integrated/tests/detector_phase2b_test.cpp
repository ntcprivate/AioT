#include "signal.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <cmath>
#include <initializer_list>
int main() {
    float beat[256];const char* issue=nullptr;
    // Weak precursor180ms before stronger QRS: refractory starts at confirmed QRS.
    for(int sign : {-1,1}) {
        BeatDetector detector;unsigned count=0;
        for(int i=0;i<950;++i) {
            int raw=2048+(i==600?sign*100:0)+(i==645?sign*500:0);
            if(detector.push(raw,i*4000LL,beat,issue)) {assert(detector.last_window().center_sample==645);assert(i==772);++count;}
            assert(!issue);
        }
        assert(count==1);
    }
    // A modestly taller late lobe must not move an already valid first fiducial.
    BeatDetector lobes;unsigned count=0;
    for(int i=0;i<900;++i) {
        if(lobes.push(2048+(i==600?500:0)+(i==620?600:0),i*4000LL,beat,issue)) {assert(lobes.last_window().center_sample==600);++count;}
        assert(!issue);
    }
    assert(count==1);
    // Absence emits the existing safety issue once but does not restart warm-up/history.
    BeatDetector absent;unsigned warnings=0;
    for(int i=0;i<2000;++i) {assert(!absent.push(2048,i*4000LL,beat,issue));if(issue){assert(strcmp(issue,"NO_RELIABLE_R_PEAK")==0);++warnings;}}
    assert(warnings==1 && absent.stats().no_peak_resets==0 && absent.stats().warmup_samples==500);
    assert(absent.stats().no_peak_events==1);
    // ADC sentinel/out-of-range and timing discontinuity never produce a window.
    BeatDetector invalid;assert(!invalid.push(-1,0,beat,issue) && strcmp(issue,"INVALID_ADC_SAMPLE")==0);
    assert(!invalid.push(65535,4000,beat,issue) && strcmp(issue,"INVALID_ADC_SAMPLE")==0);
    assert(!invalid.push(2048,8000,beat,issue) && !issue);
    assert(!invalid.push(2048,8000,beat,issue) && strcmp(issue,"BEAT_TIMING_GAP")==0);
    assert(invalid.pending_count()==0);
    // Continuous pure50Hz: both detector and existing block gate are checked elsewhere.
    BeatDetector mains;unsigned false_peaks=0;
    for(int i=0;i<7500;++i)false_peaks+=mains.push(int(std::lround(2048+100*std::sin(6.283185307179586*50*i/250))),i*4000LL,beat,issue);
    assert(false_peaks==0);
    puts("PASS: precursor confirmation, late-lobe fiducial, no-peak event without blind reset, invalid ADC/timing, pure50Hz.");
}
