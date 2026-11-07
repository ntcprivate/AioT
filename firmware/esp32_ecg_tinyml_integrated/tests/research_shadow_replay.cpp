// Real prerecorded ECG -> unchanged quality/detector/windows/preprocessing.
// HOST_REPLAY only: no serial, ADC injection, fake predictions or acceptance tuning.
#include "research_shadow.h"
#include "preprocessing.h"
#include "test_data/ecg_test_metadata.h"
#include <cstdio>
#include <cstring>
#include <fstream>
#include <vector>
#include <iterator>
int main(int argc,char** argv) {
    if(argc!=4)return 2;
    std::ifstream file(argv[1],std::ios::binary);std::vector<int16_t> input;
    int16_t sample;while(file.read(reinterpret_cast<char*>(&sample),2))input.push_back(sample);
    const size_t n=std::min(input.size(),static_cast<size_t>(std::stoull(argv[3])));
    FILE* q=std::fopen((std::string(argv[2])+".q.bin").c_str(),"wb");
    FILE* csv=std::fopen((std::string(argv[2])+".csv").c_str(),"w");if(!q || !csv)return 3;
    std::fprintf(csv,"r_index,r_t_us,end_us,generation\n");
    research::Engine engine;research::Window w;unsigned good=0,windows=0,rejected=0,invalid=0;
    for(size_t start=0;start+256<=n;start+=256) {
        int raw[256];int64_t time[256];
        for(int i=0;i<256;++i){raw[i]=input[start+i];time[i]=1000000+(start+i)*4000LL;}
        if(signal_block_reason(raw,time)){++invalid;good=0;engine.reset();continue;}
        if(++good<2)continue;
        bool blocked=false;
        for(int i=0;i<256;++i) {
            const char* issue=engine.push(raw[i],time[i],start+i,1);
            if(issue && std::strcmp(issue,"NO_RELIABLE_R_PEAK")){engine.reset();blocked=true;break;}
        }
        if(blocked)continue;
        while(engine.pop(w)) {
            int8_t bytes[256];unsigned clipped=0;
            if(!ecg_preprocessing::quantize(w.raw,bytes,kInputScale,kInputZero,clipped) || clipped){++rejected;continue;}
            std::fwrite(bytes,1,256,q);std::fprintf(csv,"%lld,%lld,%lld,%u\n",(long long)w.r_sample,(long long)w.r_us,(long long)w.end_us,w.generation);++windows;
        }
    }
    std::fclose(q);std::fclose(csv);
    std::printf("{\"source\":\"HOST_REFERENCE_REPLAY\",\"samples\":%llu,\"windows\":%u,\"rejected\":%u,\"invalid_blocks\":%u,\"queue_drops\":%u,\"queue_high\":%u}\n",(unsigned long long)n,windows,rejected,invalid,engine.drops,engine.high_water);
}
