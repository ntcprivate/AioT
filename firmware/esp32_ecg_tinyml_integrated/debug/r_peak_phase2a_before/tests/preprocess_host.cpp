#include "preprocessing.h"
#include "test_data/ecg_test_metadata.h"
#include <fstream>
#include <cstring>
#include <vector>
#include <iterator>
#include <cassert>
int main(int argc,char** argv) {
    assert(ecg_preprocessing::round_even(.5)==0 && ecg_preprocessing::round_even(1.5)==2);
    assert(ecg_preprocessing::round_even(-.5)==0 && ecg_preprocessing::round_even(-1.5)==-2);
    float constant[256]={};int8_t q[256];unsigned clipped=0;
    assert(!ecg_preprocessing::quantize(constant,q,kInputScale,kInputZero,clipped));
    if(argc!=3)return 2;
    std::ifstream input(argv[1],std::ios::binary);std::vector<char> bytes((std::istreambuf_iterator<char>(input)),{});
    if(bytes.size()%1024)return 3;
    std::ofstream output(argv[2],std::ios::binary);
    for(size_t offset=0;offset<bytes.size();offset+=1024) {
        float beat[256];memcpy(beat,bytes.data()+offset,1024);
        if(!ecg_preprocessing::quantize(beat,q,kInputScale,kInputZero,clipped))return 4;
        output.write(reinterpret_cast<const char*>(q),256);
    }
    return output?0:5;
}
