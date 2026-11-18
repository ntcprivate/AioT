// Read-only host diagnostic around unchanged production BeatDetector.
#define private public
#include "signal.h"
#undef private
#include <cstdio>
#include <fstream>
#include <vector>
#include <iterator>
#include <cstring>
int main(int argc,char**argv){
 if(argc!=2)return 2;
 std::ifstream f(argv[1],std::ios::binary);std::vector<char>b((std::istreambuf_iterator<char>(f)),{});
 if(b.size()%2)return 3;
 BeatDetector d;float w[256];
 for(size_t i=0;i<b.size()/2;++i){int16_t raw;memcpy(&raw,b.data()+2*i,2);auto n=d.counters_.candidates;const char*issue=nullptr;
 bool done=d.push(raw,i*4000LL,w,issue);
 if(d.counters_.candidates!=n)printf("candidate,%lld,%lu\n",(long long)d.last_center_,(unsigned long)i);
 if(done)printf("window,%lld,%lu\n",(long long)d.last_window().center_sample,(unsigned long)i);
 if(issue)printf("issue,%lu,%s\n",(unsigned long)i,issue);
 }
 return 0;
}
