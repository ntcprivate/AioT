// Real detector/window/preprocessing source; deterministic timestamps, not RTOS simulation.
#include <fstream>
#include <cstdio>
#include <cstdint>
#include "signal.h"
#include "preprocessing.h"
#include "test_data/ecg_test_metadata.h"
int main(int argc,char** argv){
 if(argc!=5)return 2;
 std::ifstream input(argv[1],std::ios::binary);std::ofstream events(argv[2]),quantized(argv[3],std::ios::binary),windows(argv[4],std::ios::binary);
 if(!input || !events || !quantized || !windows)return 3;
 BeatDetector detector;float beat[256];int8_t q[256];int64_t i=0;uint16_t raw;unsigned last=0;
 while(input.read(reinterpret_cast<char*>(&raw),2)){
  const char* issue=nullptr;bool ready=detector.push(raw,i*4000,beat,issue);auto stats=detector.stats();
  if(stats.candidates!=last){events<<"peak,"<<detector.detected_center()<<"\n";last=stats.candidates;}
  if(issue)events<<"issue,"<<i<<","<<issue<<"\n";
  if(ready){unsigned clips=0;bool ok=ecg_preprocessing::quantize(beat,q,kInputScale,kInputZero,clips);
   auto info=detector.last_window();events<<"window,"<<info.center_sample<<","<<int(ok)<<","<<clips<<"\n";
   if(ok && !clips){quantized.write(reinterpret_cast<char*>(q),256);windows.write(reinterpret_cast<char*>(beat),1024);}
  }++i;
 }
 events<<"samples,"<<i<<"\n";return events && quantized && windows?0:4;
}
