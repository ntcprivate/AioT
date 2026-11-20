#include "trace_transport.h"
#include <atomic>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <sys/lock.h>
namespace {
_lock_t output_lock;
std::atomic<bool> trace_active{false};
uint32_t trace_errors=0; // Accessed by the sole trace-producing AI task.
static_assert(ATOMIC_BOOL_LOCK_FREE==2,"Trace pause flag must be lock-free");
}
void console_lock() { _lock_acquire_recursive(&output_lock); flockfile(stdout); }
void console_unlock() { funlockfile(stdout); _lock_release_recursive(&output_lock); }
bool console_trace_active() { return trace_active.load(std::memory_order_acquire); }
void console_trace_start() {
    console_lock();
    trace_errors=0;
    trace_active.store(true,std::memory_order_release);
    if(fflush(stdout)!=0) { ++trace_errors; clearerr(stdout); }
    console_unlock();
}
void console_trace_stop() { trace_active.store(false,std::memory_order_release); }
uint32_t console_trace_errors() { return trace_errors; }
bool console_trace_line(const char* format,...) {
    char line[512];
    va_list args; va_start(args,format);
    const int length=vsnprintf(line,sizeof(line),format,args);
    va_end(args);
    if(length<0 || static_cast<size_t>(length)>=sizeof(line)-32) { ++trace_errors; return false; }
    uint32_t hash=2166136261u;
    for(int i=0;i<length;++i) hash=(hash^static_cast<uint8_t>(line[i]))*16777619u;
    const int suffix=snprintf(line+length,sizeof(line)-length," line_fnv=%08lx\n",static_cast<unsigned long>(hash));
    if(suffix<=0 || static_cast<size_t>(suffix)>=sizeof(line)-length) { ++trace_errors; return false; }
    console_lock();
    const bool wrote=fwrite(line,1,length+suffix,stdout)==static_cast<size_t>(length+suffix);
    const bool flushed=fflush(stdout)==0;
    if(!wrote || !flushed || ferror(stdout)) { ++trace_errors; clearerr(stdout); }
    console_unlock();
    return wrote && flushed;
}
