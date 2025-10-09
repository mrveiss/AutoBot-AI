# Connection Info Crash - Hotfix

## Issue
GUI crashes when clicking "Connection Info" tab due to unhandled exception in network detection.

## Fix Applied
Added comprehensive error handling with fallback mode to `gui/widgets/connection_info.py`.

## Manual Fix for Existing Installation

Copy the updated file from resources to your Windows installation:

```powershell
# From: resources/windows-npu-worker/gui/widgets/connection_info.py
# To: C:\AutoBot\NPU\gui\widgets\connection_info.py
```

Or reinstall by running:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

## Alternative: Copy Just the Updated Widget

If you don't want to reinstall, manually copy this one file:

1. Download/copy `gui/widgets/connection_info.py` from resources
2. Replace `C:\AutoBot\NPU\gui\widgets\connection_info.py`
3. Restart the GUI

The fix adds try-catch error handling so network detection errors won't crash the GUI.
