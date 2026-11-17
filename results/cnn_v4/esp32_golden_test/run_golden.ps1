param(
    [ValidateSet('build','size','flash-monitor','monitor')][string]$Action='build',
    [string]$Port='',
    [switch]$BenchConfirmed
)
$ErrorActionPreference='Stop'
$env:IDF_PATH='C:\esp\v5.4.4\esp-idf'
$env:IDF_TOOLS_PATH='C:\Espressif'
$env:IDF_PYTHON_ENV_PATH='C:\Espressif\tools\python\v5.4.4\venv'
# Existing installation has no constraints file. Minimum dependencies were
# checked successfully; no packages are installed/changed by this helper.
$env:IDF_PYTHON_CHECK_CONSTRAINTS='no'
$env:PATH='C:\Espressif\tools\cmake\3.30.2\bin;C:\Espressif\tools\ninja\1.12.1;C:\Espressif\tools\xtensa-esp-elf\esp-14.2.0_20260121\xtensa-esp-elf\bin;C:\Espressif\tools\python\v5.4.4\venv\Scripts;'+$env:PATH
$idfPython=Join-Path $env:IDF_PYTHON_ENV_PATH 'Scripts\python.exe'
$idfScript=Join-Path $env:IDF_PATH 'tools\idf.py'
$project=Join-Path $PSScriptRoot 'firmware'
switch($Action){
    'build' { & $idfPython $idfScript -C $project build }
    'size' { & $idfPython $idfScript -C $project size }
    'flash-monitor' {
        if(!$BenchConfirmed -or !$Port){throw 'Specify -Port and -BenchConfirmed for bench-only flash/reset.'}
        & $idfPython $idfScript -C $project -p $Port flash monitor
    }
    'monitor' {
        if(!$Port){throw 'Specify -Port.'}
        & $idfPython $idfScript -C $project -p $Port monitor
    }
}
if($LASTEXITCODE -ne 0){throw "ESP-IDF failed with exit code $LASTEXITCODE"}
