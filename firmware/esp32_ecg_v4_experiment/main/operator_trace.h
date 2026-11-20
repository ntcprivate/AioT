#pragma once
// Diagnostic only: capture output at operator completion BEFORE arena reuse.
// No printing/allocation in profiler callbacks; no preserve_all_tensors change.
#include <cstdint>
#include <cstdio>
#include <cstring>
#include "trace_transport.h"
#include "trace_codec.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_profiler_interface.h"
#include "tensorflow/lite/micro/schema/schema_generated.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

namespace ecg_debug {
class Interpreter : public tflite::MicroInterpreter {
public:
    using tflite::MicroInterpreter::MicroInterpreter;
    TfLiteEvalTensor* eval(int index) {
        const auto& c=context(); // Protected accessor in the pinned TFLM1.4.2 API.
        return c.GetEvalTensor(const_cast<TfLiteContext*>(&c),index);
    }
};
inline uint32_t fnv(const uint8_t* p,size_t n) {
    uint32_t h=2166136261u;
    for(size_t i=0;i<n;++i) h=(h^p[i])*16777619u;
    return h;
}
class Trace : public tflite::MicroProfilerInterface {
public:
    void attach(Interpreter* instance,const tflite::Model* model) { interpreter_=instance; model_=model; }
    void begin(unsigned sample) { sample_=sample; count_=used_=0; active_=true; failed_=false; }
    uint32_t BeginEvent(const char* tag) override {
        if(!active_) return UINT32_MAX;
        const uint32_t index=count_++;
        if(index>=32) { failed_=true; return UINT32_MAX; }
        records_[index].tag=tag;
        return index;
    }
    void EndEvent(uint32_t index) override {
        if(!active_ || index==UINT32_MAX) return;
        const auto* graph=model_->subgraphs()->Get(0);
        if(index>=graph->operators()->size()) { failed_=true; return; }
        const auto* op=graph->operators()->Get(index);
        // The fixed model has exactly one output per node. Reject other schemas.
        if(op->outputs()->size()!=1) { failed_=true; return; }
        auto& r=records_[index]; r.tensor=op->outputs()->Get(0);
        auto* tensor=interpreter_->eval(r.tensor);
        if(!tensor || !tensor->dims || !tensor->data.raw) { failed_=true; return; }
        size_t size=1;
        for(int i=0;i<tensor->dims->size;++i) {
            if(tensor->dims->data[i]<=0) { failed_=true; return; }
            size*=tensor->dims->data[i];
        }
        if(tensor->type==kTfLiteInt32 || tensor->type==kTfLiteFloat32) size*=4;
        else if(tensor->type==kTfLiteInt64) size*=8;
        else if(tensor->type!=kTfLiteInt8) { failed_=true; return; }
        if(used_+size>sizeof(bytes_)) { failed_=true; return; }
        r.offset=used_; r.size=size;
        const auto* code=model_->operator_codes()->Get(op->opcode_index());
        r.version=code->version();
        memcpy(bytes_+used_,tensor->data.raw,size); used_+=size;
    }
    bool finish_and_print(const int8_t* source,bool invoke_ok,int output_code) {
        active_=false;
        const auto* graph=model_->subgraphs()->Get(0);
        if(count_!=graph->operators()->size()) failed_=true;
        console_trace_start(); // Suppress ADC summary output only, never sampling.
        bool ok=console_trace_line("ECG_TRACE_BEGIN protocol=2 sample=%u input_fnv=%08lx nodes=%u model_schema=%u chunk_bytes=16 bytes_total=%u status=%s",
            sample_,static_cast<unsigned long>(fnv(reinterpret_cast<const uint8_t*>(source),256)),count_,
            static_cast<unsigned>(model_->version()),static_cast<unsigned>(used_),failed_?"FAILED":"CAPTURED");
        unsigned chunks=0,generation_errors=0;
        if(!failed_) for(unsigned i=0;i<count_;++i) {
            const auto& r=records_[i];
            const auto* q=graph->tensors()->Get(r.tensor)->quantization();
            ok=console_trace_line("ECG_TRACE_TENSOR sample=%u op=%u tag=%s version=%d tensor=%d bytes=%u fnv=%08lx scale=%.12g zero=%lld",
                sample_,i,r.tag,r.version,r.tensor,static_cast<unsigned>(r.size),
                static_cast<unsigned long>(fnv(bytes_+r.offset,r.size)),q && q->scale() && q->scale()->size()?q->scale()->Get(0):0,
                static_cast<long long>(q && q->zero_point() && q->zero_point()->size()?q->zero_point()->Get(0):0)) && ok;
            for(size_t start=0;start<r.size;start+=16) {
                const size_t n=r.size-start<16?r.size-start:16;
                char hex[33];
                // Exactly two nibble assignments per byte, explicit terminator.
                if(!encode_hex(bytes_+r.offset+start,n,hex,sizeof(hex)) || strlen(hex)!=2*n) {
                    ++generation_errors; ok=false; break;
                }
                ok=console_trace_line("ECG_TRACE_DATA sample=%u op=%u tensor=%d offset=%u nbytes=%u hex_chars=%u chunk_fnv=%08lx hex=%s",
                    sample_,i,r.tensor,static_cast<unsigned>(start),static_cast<unsigned>(n),static_cast<unsigned>(2*n),
                    static_cast<unsigned long>(fnv(bytes_+r.offset+start,n)),hex) && ok;
                ++chunks;
                vTaskDelay(1); // Outside Invoke, lower-priority AI task only.
            }
        }
        const bool complete=ok && !failed_ && generation_errors==0 && console_trace_errors()==0;
        ok=console_trace_line("ECG_TRACE_END sample=%u nodes=%u bytes_total=%u chunks_total=%u stream_fnv=%08lx generation_errors=%u write_errors=%lu status=%s",
            sample_,count_,static_cast<unsigned>(used_),chunks,static_cast<unsigned long>(fnv(bytes_,used_)),
            generation_errors,static_cast<unsigned long>(console_trace_errors()),complete?"COMPLETE":"FAILED") && ok;
        ok=console_trace_line("ECG_TRACE_RESULT sample=%u code=%d invoke_ok=%d timing_instrumented=1 trace_ok=%d write_errors=%lu",
            sample_,output_code,invoke_ok,complete && ok,static_cast<unsigned long>(console_trace_errors())) && ok;
        console_trace_stop();
        return complete && ok && invoke_ok;
    }

private:
    struct Record { const char* tag=nullptr; int tensor=0,version=0; size_t offset=0,size=0; };
    Interpreter* interpreter_=nullptr; const tflite::Model* model_=nullptr;
    bool active_=false,failed_=false; unsigned sample_=0,count_=0; size_t used_=0;
    Record records_[32]; uint8_t bytes_[24*1024];
};
} // namespace ecg_debug
