#include "signal.h"
#include <cstdio>
#include <fstream>
#include <iterator>
#include <vector>
#include <cstring>
int main(int argc,char** argv) {
    if(argc!=2)return 2;
    std::ifstream file(argv[1],std::ios::binary);
    std::vector<char> bytes((std::istreambuf_iterator<char>(file)),{});
    if(!file && !file.eof())return 3;
    if(bytes.size()%2)return 4;
    BeatDetector detector,gated;float beat[256];unsigned good_blocks=0;bool block_allowed=false;
    for(size_t i=0;i<bytes.size()/2;++i) {
        int16_t raw;memcpy(&raw,bytes.data()+2*i,2);const char* issue=nullptr;
        if(i%256==0) {
            if(i+256<=bytes.size()/2) {
                int block[256];int64_t times[256];
                for(size_t j=0;j<256;++j) {int16_t x;memcpy(&x,bytes.data()+2*(i+j),2);block[j]=x;times[j]=(i+j)*4000;}
                const char* q=signal_block_reason(block,times);
                printf("quality,%lu,%s\n",static_cast<unsigned long>(i),q?q:"PASS");
                if(q) {good_blocks=0;gated.reset();}else if(good_blocks<2)++good_blocks;
                block_allowed=!q && good_blocks>=2;
            }else block_allowed=false;
        }
        if(detector.push(raw,static_cast<int64_t>(i)*4000,beat,issue))printf("peak,%lu\n",static_cast<unsigned long>(i-127));
        if(issue)printf("issue,%lu,%s\n",static_cast<unsigned long>(i),issue);
        issue=nullptr;
        if(block_allowed && gated.push(raw,static_cast<int64_t>(i)*4000,beat,issue))printf("gated_peak,%lu\n",static_cast<unsigned long>(i-127));
        if(issue)printf("gated_issue,%lu,%s\n",static_cast<unsigned long>(i),issue);
    }
}
