// TEST_ONLY fixtures from preserved real Validation assets; not live ECG.
#pragma once
#include <cstddef>
constexpr size_t kAiTestCount=20;
constexpr char kAiTestRawSha[]="b55642468e1fa654b368f874d6370a469b21c94ad5898c60f8a339ac1f022351";
constexpr char kAiTestExtendedSha[]="ca78d98e03da93c8e4141b517935da1fe5931ffa72dbd1d8c2f58e443850fce7";
struct AiTestCase {const char* id;const char* record;int label;char symbol;int code;};
constexpr AiTestCase kAiTestCases[kAiTestCount]={
  {"golden0","115",0,'N',-126},
  {"golden1","233",0,'N',50},
  {"golden2","214",1,'V',-66},
  {"golden3","233",1,'V',68},
  {"golden4","121",0,'N',7},
  {"golden5","210",1,'V',7},
  {"golden6","210",0,'N',-124},
  {"golden7","234",0,'N',-126},
  {"golden8","121",0,'N',-125},
  {"golden9","233",1,'V',47},
  {"golden10","210",0,'N',-126},
  {"golden11","115",0,'N',-126},
  {"fc14_118_5613","118",-1,'R',-53},
  {"fc14_118_12239","118",-1,'R',68},
  {"fc14_118_416969","118",-1,'R',-115},
  {"fc14_210_200430","210",1,'V',105},
  {"fc14_214_22287","214",-1,'L',-108},
  {"fc14_233_20069","233",1,'V',-3},
  {"fc14_233_59286","233",0,'N',-20},
  {"fc14_233_291311","233",0,'N',-92},
};
