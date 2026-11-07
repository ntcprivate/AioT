"""Offline audit only. Never opens a serial port or modifies protected sources."""
from pathlib import Path
import difflib
import hashlib
import json

FW = Path(__file__).resolve().parents[1]
ROOT = FW.parents[1]
APP = ROOT / 'tools/ecg_monitor'
DEBUG = FW / 'debug'
BEFORE = DEBUG / 'telemetry_fix_before'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

protected = json.loads((BEFORE / 'protected_sha256.json').read_text())
protected_check = {name: sha(FW / name) == digest for name, digest in protected.items()}
original = json.loads((FW / 'source_project_hashes.json').read_text())
original_check = {name: sha(ROOT / name) == digest for name, digest in original.items()}
assert all(protected_check.values()), protected_check
assert all(original_check.values()), original_check

baseline = json.loads((BEFORE / 'source_sha256.json').read_text())
changes = []
patch = []
for name, digest in baseline.items():
    path = ROOT / name
    if sha(path) != digest:
        saved = BEFORE / name
        assert saved.exists(), saved
        changes.append(name)
        patch.extend(difflib.unified_diff(saved.read_text(encoding='utf-8-sig').splitlines(True),
            path.read_text(encoding='utf-8-sig').splitlines(True),
            fromfile='snapshot/' + name.replace('\\', '/'), tofile='current/' + name.replace('\\', '/')))
(DEBUG / 'telemetry_final_diff.patch').write_text(''.join(patch), encoding='utf-8')

additional = [
    APP / 'benchmark_transport.py', APP / 'diagnose_capture.py',
    APP / 'tests/test_telemetry_fix.py', FW / 'tests/telemetry_wire_test.cpp',
    FW / 'docs/telemetry_reliability_review.md', FW / 'docs/telemetry_protocol.md',
    APP / 'README.md', FW / 'README.md', ROOT / 'README.md',
    DEBUG / 'sdkconfig.synthetic_test', Path(__file__).resolve(),
]
chain = json.loads((APP / 'reports/offline_validation.json').read_text())['chain']
assert chain['beats'] == 9425 and chain['cnn_mismatched_codes'] == 0
assert chain['preprocessing_mismatched_bytes'] == 0
tests = (APP / 'reports/telemetry_fix_tests.log').read_text(encoding='utf-8-sig')
assert 'Ran 42 tests' in tests and '\nOK' in tests
golden_bytes = (DEBUG / 'telemetry_fix_golden.log').read_bytes()
golden = golden_bytes.decode('utf-16' if golden_bytes.startswith(b'\xff\xfe') else
    'utf-16-le' if b'\x00' in golden_bytes else 'utf-8-sig')
assert golden.count('exact=1 repeats=33 stable=1') == 12 and 'failed=0' in golden

artifacts = {}
for build in ('build', 'build_synthetic_telemetry_test'):
    path = FW / build / 'esp32_ecg_tinyml_integrated.bin'
    artifacts[build] = dict(bytes=path.stat().st_size, sha256=sha(path))

report = dict(
    date='2026-11-06', status='HOST_CHECKS_AND_BOTH_BUILDS_PASS_PENDING_HARDWARE_VALIDATION',
    continued_files=json.loads((DEBUG / 'telemetry_resume_files.json').read_text()),
    git='NOT_A_GIT_REPOSITORY; snapshot diffs retained; no reset/clean/revert',
    changed_relative_to_snapshot=changes,
    modified_or_new_additional_files=[str(p.relative_to(ROOT)) for p in additional],
    final_source_sha256={str((ROOT / p).relative_to(ROOT)): sha(ROOT / p) for p in changes},
    additional_sha256={str(p.relative_to(ROOT)): sha(p) for p in additional},
    protected_source_checks=protected_check, original_project_checks=original_check,
    tests=dict(monitor_python=42, legacy_operator_trace_python=14,
        cpp=['system', 'signal', 'lead_off', 'trace_codec', 'telemetry_wire'],
        cpp_python_wire_samples=16000, virtual_long_stream_samples=320000,
        golden_samples=12, golden_repeats_each=33, parity=chain),
    transport_load=json.loads((APP / 'reports/transport_load.json').read_text()),
    idf='5.4.4', build_artifacts=artifacts,
    hardware_config=dict(adc_gpio=34, lo_plus_gpio=27, lo_minus_gpio=26, led_gpio=23,
        buzzer_gpio=25, target_hz=250, threshold=.52, live_unlocked=False),
    crc_hardware_root_cause='UNPROVEN: new failing raw capture not available',
    hardware_validation='PENDING HARDWARE VALIDATION',
    com_opened=False, flashed=False, reset=False,
    report='docs/telemetry_reliability_review.md',
)
for path in (DEBUG / 'telemetry_fix_report.json', APP / 'reports/telemetry_fix_report.json'):
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(dict(protected=len(protected_check), original_project_files=len(original_check),
    changed_snapshot_files=len(changes), artifacts=artifacts, result='PASS'), indent=2))
