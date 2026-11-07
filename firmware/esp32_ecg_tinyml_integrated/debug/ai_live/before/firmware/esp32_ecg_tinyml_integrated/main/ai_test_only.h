#pragma once
#include <cstdint>
bool ai_test_only_begin();
void ai_test_only_note_golden(unsigned sample,unsigned run,int code,int64_t inference_us,bool ok);
void ai_test_only_note_golden_result(unsigned sample,bool exact);
bool ai_test_only_finish(bool golden_passed);
