# GitHub backup and setup on another Windows laptop

The repository contains source, model checkpoints and research reports. Python
environments, downloaded ECG datasets, installers and regenerable ESP-IDF build
directories are local resources, not source code. Existing raw research captures
and deliberately preserved firmware snapshots are not deleted by this repair.

## Clone and retrieve research artifacts

Install Git and Git LFS, then run:

```powershell
git lfs install
git clone https://github.com/ntcprivate/AioT.git
cd AioT
git lfs pull
git lfs ls-files
```

These two large research artifacts use LFS:

- `results/cnn_v2/train_only.npz`
- `results/model_improvement/next_direction_analysis/beat_diagnostics.json`

Their full contents must be uploaded to the GitHub LFS endpoint when pushing.
A text pointer alone is not a completed backup. LFS account storage/bandwidth
availability must permit that upload. The repair also keeps verified local copies
and the original files; see the local `git_repair_backup_<timestamp>/` manifest.

Do not use `git push --all`, `--mirror` or `--force` for this repair. The repaired
`main` retains the existing remote main as its parent and can use a normal
`git push origin main`. Older generated build objects already on the remote remain
in its history; this repair does not rewrite published commits.

## ECG Monitor 2.0

Install Python 3.13 with Python Launcher (the existing setup script targets 3.13).
From the cloned repository:

```powershell
cd tools/ecg_monitor
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -c "import PySide6,pyqtgraph,serial,numpy,scipy; print('Imports OK')"
.\.venv\Scripts\python.exe run.py
```

Alternatively use `setup.bat`, then `Start_ECG_Monitor.bat`. The environment is
created on the new laptop; copying installed TensorFlow DLLs or a `.venv` from
another PC is not a substitute for installation. Monitor does not run the CNN;
model inference stays on ESP32. Launching Monitor alone does not authorize a
hardware measurement.

## Other research and firmware dependencies

Keep training environments separate from the Monitor environment. Use the
version/configuration recorded for each experiment rather than installing a
different TensorFlow and assuming numerical parity. Downloaded MIT-BIH/INCART and
other ECG datasets must be restored separately at the paths expected by the saved
protocols; retain original headers and checksums. No dataset is recreated by Git.

Use ESP-IDF 5.4.4 for V4 firmware. Build directories are regenerated. Managed
components are downloaded using the component manifests; V4 currently references
the integrated project's managed component locations, so restore those declared
dependencies before configuring the V4 experiment. Do not change kernels/model
or treat a fresh build as a replacement for archived hardware evidence.

## Local recovery

Before amendment, the complete original Git history and refs were saved in
`git_repair_backup_<timestamp>/repository_before.bundle` and checked with
`git bundle verify`. The original index, ignore file and commit ID are also saved.
To inspect the original history without altering the working project:

```powershell
git clone PATH_TO_BACKUP/repository_before.bundle AioT-before-repair
```

No garbage collection or deletion of original project data is required. Keep the
bundle off GitHub and copy it to another disk for independent disaster recovery.
