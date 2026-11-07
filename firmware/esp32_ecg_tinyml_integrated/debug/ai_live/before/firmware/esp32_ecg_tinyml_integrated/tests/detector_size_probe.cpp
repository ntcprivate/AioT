#include "signal.h"
// Cross-compile only: ELF symbol sizes give actual ESP32 C++ layout without a board.
extern "C" {char phase2a_detector_size[sizeof(BeatDetector)];}
#if PHASE2A_CURRENT
extern "C" {char phase2a_window_buffer_size[sizeof(BeatWindowBuffer)];}
#endif
