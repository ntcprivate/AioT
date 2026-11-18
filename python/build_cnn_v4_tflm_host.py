import concurrent.futures
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "firmware/esp32_ecg_tinyml_integrated"
COMPONENT = PROJECT / "managed_components/espressif__esp-tflite-micro"
MICRO = COMPONENT / "tensorflow/lite/micro"
OUT = ROOT / "results/cnn_v4/tflm_host_build"
OUT.mkdir(parents=True, exist_ok=True)
core = ["debug_log", "flatbuffer_conversions", "flatbuffer_utils", "memory_helpers", "micro_allocation_info",
        "micro_allocator", "micro_common", "micro_context", "micro_interpreter_context", "micro_interpreter_graph",
        "micro_interpreter", "micro_log", "micro_op_resolver", "micro_profiler", "micro_resource_variable",
        "micro_time", "micro_utils", "recording_micro_allocator", "system_setup"]
sources = [MICRO / (name + ".cc") for name in core]
sources += list((MICRO / "arena_allocator").glob("*.cc")) + list((MICRO / "memory_planner").glob("*.cc"))
sources += [MICRO / "kernels" / (name + ".cc") for name in
            ["conv_common", "fully_connected_common", "logistic_common", "pooling_common", "reduce_common",
             "kernel_util", "expand_dims", "reshape", "reshape_common"]]
sources += [MICRO / "kernels/esp_nn" / (name + ".cc") for name in
            ["conv", "fully_connected", "logistic", "pooling", "reduce"]]
sources += [MICRO / "kernels/internal" / (name + ".cc") for name in
            ["common", "portable_tensor_utils", "quantization_util", "runtime_shape", "tensor_ctypes"]]
sources += [PROJECT / "main/single_round_conv.cpp", PROJECT / "main/single_round_fc.cpp",
            ROOT / "results/cnn_v4/v4_full_chain_host.cpp"]
flags = ["g++", "-std=c++17", "-O2", "-DNDEBUG", "-DECG_HOST_TEST=1", "-DTF_LITE_STATIC_MEMORY",
         "-DTFLITE_SINGLE_ROUNDING=0", "-DECG_CONV_SINGLE_ROUNDING=1",
         "-I" + str(PROJECT / "tests/host_stubs"), "-I" + str(PROJECT / "main"), "-I" + str(COMPONENT),
         "-I" + str(COMPONENT / "third_party/flatbuffers/include"), "-ffunction-sections", "-fdata-sections"]


def compile_one(pair):
    index, source = pair
    obj = OUT / f"{index}.o"
    result = subprocess.run(flags + ["-c", str(source), "-o", str(obj)], capture_output=True, text=True)
    if result.returncode: raise RuntimeError(f"{source}\n{result.stderr}")
    return obj


with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    objects = list(pool.map(compile_one, enumerate(sources)))
exe = ROOT / "results/cnn_v4/v4_tflm_host.exe"
subprocess.run(["g++", *map(str, objects), "-Wl,--gc-sections", "-o", str(exe)], check=True)
print(exe)
