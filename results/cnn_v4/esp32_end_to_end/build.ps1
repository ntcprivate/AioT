param([ValidateSet('ADC','REPLAY','BENCH_INT8','BENCH_FP32')][string]$Mode='ADC',
      [ValidateSet('MITBIH_100','INCART_I08','INCART_PVC_V1')][string]$Record='MITBIH_100',
      [string]$BuildDirectory='')
$ErrorActionPreference='Stop'
$env:IDF_PATH='C:\esp\v5.4.4\esp-idf'
$env:IDF_TOOLS_PATH='C:\Espressif'
$env:IDF_PYTHON_ENV_PATH='C:\Espressif\tools\python\v5.4.4\venv'
$env:IDF_PYTHON_CHECK_CONSTRAINTS='no'
$env:PATH='C:\Espressif\tools\cmake\3.30.2\bin;C:\Espressif\tools\ninja\1.12.1;C:\Espressif\tools\xtensa-esp-elf\esp-14.2.0_20260121\xtensa-esp-elf\bin;C:\Espressif\tools\python\v5.4.4\venv\Scripts;'+$env:PATH
$root=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$project=Join-Path $root 'firmware/esp32_ecg_v4_experiment'
$build=Join-Path $project ('build_'+$Mode.ToLower()+'_'+$Record)
if($BuildDirectory){$build=$BuildDirectory}
$idfPython=Join-Path $env:IDF_PYTHON_ENV_PATH 'Scripts/python.exe'
$idfScript=Join-Path $env:IDF_PATH 'tools/idf.py'
if($Mode -eq 'REPLAY' -and !(Test-Path (Join-Path $project "main/assets/$Record.bin"))){throw 'BLOCKED: run prepare_v4_replay_assets.py using restored original Python 3.11 environment.'}
if($Mode -eq 'BENCH_FP32' -and !(Test-Path (Join-Path $project 'main/model/ecg_cnn_v4_fp32.tflite'))){throw 'BLOCKED: FP32 export not yet available.'}
& $idfPython $idfScript -C $project -B $build -D "ECG_EXPERIMENT_MODE=$Mode" -D "ECG_REPLAY_RECORD=$Record" reconfigure
if($LASTEXITCODE -ne 0){throw 'ESP-IDF reconfigure failed'}
# Explicit one job on Windows; never invoke flash/monitor/reset here.
& ninja -C $build -j1
if($LASTEXITCODE -ne 0){throw 'Ninja build failed'}
& ninja -C $build -j1 size
if($LASTEXITCODE -ne 0){throw 'Size command failed'}
