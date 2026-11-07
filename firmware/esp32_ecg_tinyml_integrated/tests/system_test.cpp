#include "system_state.h"
#include "telemetry_codec.h"
#include "signal.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <initializer_list>
int main() {
    assert(!recovery_allowed(EcgState::Invalid,false,511,2,true));
    assert(!recovery_allowed(EcgState::Invalid,false,512,1,true));
    assert(!recovery_allowed(EcgState::Invalid,false,512,2,false));
    assert(!recovery_allowed(EcgState::Invalid,true,512,2,true));
    assert(!recovery_allowed(EcgState::Fault,true,512,2,true));
    assert(recovery_allowed(EcgState::Invalid,false,512,2,true));
    for(auto s:{EcgState::Waiting,EcgState::Collecting,EcgState::Invalid,EcgState::Fault}) {
        int lit=0;
        for(int64_t t=0;t<2000000;t+=1000) {auto p=alert_pattern(s,t);assert(!p.buzzer);lit+=p.led;}
        assert(lit>0 && lit<2000); // No steady NORMAL appearance when not classifying.
    }
    assert(alert_pattern(EcgState::Normal,123).led && !alert_pattern(EcgState::Normal,123).buzzer);
    assert(alert_pattern(EcgState::Pvc,0).buzzer && !alert_pattern(EcgState::Pvc,150000).buzzer);
    assert(ecg_wire::crc32(reinterpret_cast<const uint8_t*>("123456789"),9)==0xcbf43926u);
    uint8_t sample[7];ecg_wire::sample(sample,4001,-1,5);
    assert(sample[0]==0xa1 && sample[1]==0x0f && sample[2]==0 && sample[3]==0 && sample[4]==255 && sample[5]==255 && sample[6]==5);
    int raw[256];int64_t t[256];
    for(int i=0;i<256;++i) {raw[i]=2048+static_cast<int>(100*std::sin(6.283185307179586*50*i/250));t[i]=i*4000;}
    auto m=signal_metrics(raw);assert(m.power50_ratio>.9 && m.diff_percent>25);
    assert(strcmp(signal_block_reason(raw,t),"HIGH_FREQUENCY_NOISE")==0);
    raw[12]=4095;assert(signal_metrics(raw).clips==1);
    puts("PASS: input recovery; LED/buzzer nonblocking patterns; CRC32 golden; exact sample encoding;50Hz rejection/metrics and clipping.");
}
