# Scripts Agent Reference

This folder contains Docker start/stop scripts for each target OS.

## Scripts

- Windows PowerShell: `start-windows.ps1`, `stop-windows.ps1`
- Linux shell: `start-linux.sh`, `stop-linux.sh`
- macOS shell: `start-mac.sh`, `stop-mac.sh`

Each start script builds image `pm-mvp`, replaces any existing `pm-mvp` container, and runs it on port `8000`.