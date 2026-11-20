#pragma once
#include <cstdint>
#include <cstddef>
constexpr size_t kSampleCount=22,kSamplesPerBeat=256,kModelBytes=8688;
constexpr float kThreshold=0.88f;
constexpr int kThresholdCode=98;
constexpr float kInputScale=0.06217966973781586f,kOutputScale=0.00390625f;
constexpr int kInputZero=-8,kOutputZero=-128;
constexpr char kModelSha[]="a7ce1ed87e781597d6bbe09901602c801c08863e3ad0c3313f3a234f86719b0e";
constexpr char kSamplesSha[]="288186f6d6bc860ae5fc71f77131f2d6e5723c4471244b27747d377469ff1ed4";
struct Golden {int dataset_index;const char* record;int label,output;float score;int predicted;};
constexpr Golden kGolden[kSampleCount]={
{0,"I08",0,-120,0.031250000f,0},
{1,"I08",0,-120,0.031250000f,0},
{2,"I08",0,-120,0.031250000f,0},
{3,"I08",0,-120,0.031250000f,0},
{88,"I08",1,74,0.789062500f,0},
{92,"I08",1,114,0.945312500f,1},
{95,"I08",1,44,0.671875000f,0},
{98,"I08",1,112,0.937500000f,1},
{137,"I08",1,127,0.996093750f,1},
{144,"I08",1,127,0.996093750f,1},
{1273,"I08",0,98,0.882812500f,1},
{1662,"I08",1,-117,0.042968750f,0},
{1762,"I08",0,127,0.996093750f,1},
{1768,"I08",0,127,0.996093750f,1},
{18063,"I65",0,98,0.882812500f,1},
{18492,"I65",0,98,0.882812500f,1},
{18554,"I65",1,98,0.882812500f,1},
{22066,"I67",0,98,0.882812500f,1},
{22372,"I67",1,98,0.882812500f,1},
{23898,"I67",1,98,0.882812500f,1},
{24516,"I67",1,98,0.882812500f,1},
{24975,"I67",1,-118,0.039062500f,0},
};
