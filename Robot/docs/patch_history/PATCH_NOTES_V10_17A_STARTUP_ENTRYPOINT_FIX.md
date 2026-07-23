# BX1 V10.17A Startup Entrypoint Fix

Fixes startup regression where manual commands and some service launchers expected `main.py` in the project root while the application entry point lives at `python/main.py`.

Changes:
- Adds root `main.py` compatibility launcher.
- Updates `START_BX1_WEB.sh` to run the root compatibility launcher.
- Updates `tools/run_robot_body.sh` to check both root `main.py` and `python/main.py` before starting.
- Updates service installer to use `Restart=on-failure` instead of `Restart=always`, preventing endless clean-exit loops.
- Improves diagnosis output to show file sizes for both entry points.
