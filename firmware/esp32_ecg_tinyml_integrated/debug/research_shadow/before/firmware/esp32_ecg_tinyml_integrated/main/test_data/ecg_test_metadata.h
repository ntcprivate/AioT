// Generated from real saved Validation data. Do not edit.
#pragma once
#include <cstdint>
#include <cstddef>
constexpr size_t kSampleCount = 12;
constexpr size_t kSamplesPerBeat = 256;
constexpr size_t kModelBytes = 8560;
constexpr float kThreshold = 0.52f;
constexpr float kInputScale = 0.053921569138765335f;
constexpr int kInputZero = -27;
constexpr float kOutputScale = 0.00390625f;
constexpr int kOutputZero = -128;
constexpr char kModelSha[] = "38705f5399ada9b87f466725608a053ae2305295a8a3cae7bda01f4928f4a394";
constexpr char kSamplesSha[] = "12d63c89086b3615a92bee11914825cce9fd0d5bd11f41599d1281f00475b758";
struct Golden { int dataset_index; const char* record; int label; int output; float score; int predicted; };
constexpr Golden kGolden[kSampleCount] = {
  {19766, "115", 0, -126, 0.007812500f, 0},
  {78432, "233", 0, 50, 0.695312500f, 1},
  {56558, "214", 1, -66, 0.242187500f, 0},
  {76710, "233", 1, 68, 0.765625000f, 1},
  {28388, "121", 0, 7, 0.527343750f, 1},
  {50805, "210", 1, 7, 0.527343750f, 1},
  {52318, "210", 0, -124, 0.015625000f, 0},
  {81870, "234", 0, -126, 0.007812500f, 0},
  {27174, "121", 0, -125, 0.011718750f, 0},
  {76481, "233", 1, 47, 0.683593750f, 1},
  {52498, "210", 0, -126, 0.007812500f, 0},
  {19095, "115", 0, -126, 0.007812500f, 0},
};
