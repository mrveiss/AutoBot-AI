# AutoBot NPU Worker GUI - File Index

Complete file structure and navigation guide for the GUI application.

## 📁 Directory Structure

```
deployment/windows-npu-worker/
│
├── gui/                                 # Main GUI application
│   ├── main.py                         # Application entry point
│   ├── __init__.py                     # Package initialization
│   ├── README.md                       # Complete user documentation
│   │
│   ├── windows/                        # Main application windows
│   │   ├── __init__.py
│   │   ├── main_window.py             # Dashboard with tabs and controls
│   │   ├── settings_dialog.py         # Configuration dialog
│   │   └── log_viewer.py              # Real-time log viewer
│   │
│   ├── widgets/                        # Reusable UI components
│   │   ├── __init__.py
│   │   ├── status_panel.py            # NPU status and metrics
│   │   └── metrics_display.py         # Performance charts
│   │
│   ├── controllers/                    # Business logic
│   │   ├── __init__.py
│   │   ├── worker_controller.py       # Worker process management
│   │   └── config_manager.py          # Configuration handling
│   │
│   ├── utils/                          # Utility modules
│   │   ├── __init__.py
│   │   ├── app_config.py              # Application configuration
│   │   └── tray_icon.py               # System tray management
│   │
│   └── resources/                      # Application resources
│       └── icons/                      # Icon files
│           └── README.md              # Icon guidelines
│
├── requirements-gui.txt                # GUI dependencies
├── launch-gui.ps1                      # PowerShell launcher
├── launch-gui.bat                      # Batch launcher
├── GUI_IMPLEMENTATION.md               # Technical documentation
├── QUICK_START_GUI.md                  # Quick start guide
└── GUI_FILES_INDEX.md                  # This file
```

## 📄 File Descriptions

### Entry Points

| File | Purpose | Lines |
|------|---------|-------|
| `gui/main.py` | Application entry point, initializes PySide6 app | 50 |
| `launch-gui.ps1` | PowerShell launcher with dependency checks | 60 |
| `launch-gui.bat` | Batch file launcher | 30 |

### Main Windows

| File | Purpose | Lines |
|------|---------|-------|
| `gui/windows/main_window.py` | Main dashboard window with tabs, controls, tray | 380 |
| `gui/windows/settings_dialog.py` | Configuration dialog with YAML editor | 380 |
| `gui/windows/log_viewer.py` | Real-time log viewer with export | 190 |

### Widgets

| File | Purpose | Lines |
|------|---------|-------|
| `gui/widgets/status_panel.py` | NPU status, tasks, models display | 150 |
| `gui/widgets/metrics_display.py` | Performance metrics and history | 180 |

### Controllers

| File | Purpose | Lines |
|------|---------|-------|
| `gui/controllers/worker_controller.py` | Worker process control, API calls | 180 |
| `gui/controllers/config_manager.py` | YAML config management, backups | 150 |

### Utilities

| File | Purpose | Lines |
|------|---------|-------|
| `gui/utils/app_config.py` | Path management, configuration | 50 |
| `gui/utils/tray_icon.py` | System tray icon helper | 60 |

### Documentation

| File | Purpose | Lines |
|------|---------|-------|
| `gui/README.md` | Complete user guide and documentation | 450 |
| `GUI_IMPLEMENTATION.md` | Technical implementation details | 500 |
| `QUICK_START_GUI.md` | Quick start guide | 200 |
| `gui/resources/icons/README.md` | Icon creation guidelines | 30 |
| `GUI_FILES_INDEX.md` | This file - navigation guide | 150 |

### Configuration

| File | Purpose |
|------|---------|
| `requirements-gui.txt` | PySide6 and GUI dependencies |
| `gui/__init__.py` | Package metadata |

## 🔍 Quick Navigation

### To modify UI layout:
→ `gui/windows/main_window.py` - Main window layout and tabs
→ `gui/widgets/status_panel.py` - Status display layout
→ `gui/widgets/metrics_display.py` - Metrics visualization

### To change service control:
→ `gui/controllers/worker_controller.py` - Process management
→ `gui/windows/main_window.py` - Control button handlers

### To update configuration handling:
→ `gui/controllers/config_manager.py` - YAML operations
→ `gui/windows/settings_dialog.py` - Settings UI

### To modify log viewing:
→ `gui/windows/log_viewer.py` - Log display and streaming

### To customize tray behavior:
→ `gui/windows/main_window.py` - Tray integration
→ `gui/utils/tray_icon.py` - Tray icon helper

### To add new features:
1. Create widget in `gui/widgets/` if reusable
2. Create window in `gui/windows/` if standalone
3. Create controller in `gui/controllers/` for logic
4. Connect with signals/slots in main_window.py

## 📊 Code Statistics

| Category | Files | Lines | Purpose |
|----------|-------|-------|---------|
| Entry Points | 3 | 140 | Application startup |
| Windows | 3 | 950 | Main UI windows |
| Widgets | 2 | 330 | Reusable components |
| Controllers | 2 | 330 | Business logic |
| Utilities | 2 | 110 | Helper functions |
| Documentation | 5 | 1,600 | User guides |
| **Total** | **17** | **3,460** | **Complete GUI** |

## 🔗 Dependencies

### Primary Dependencies (requirements-gui.txt)
- PySide6 >= 6.6.0 - Qt framework
- PyYAML >= 6.0.1 - YAML parsing
- requests >= 2.31.0 - HTTP API calls
- psutil >= 5.9.0 - System monitoring

### Import Map

```python
# Main Application
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QThread
from PySide6.QtGui import QIcon, QAction

# Configuration
import yaml
from pathlib import Path

# API Communication
import requests
import subprocess

# System
import sys
from datetime import datetime
from collections import deque
```

## 🧩 Component Relationships

```
main.py (Entry)
    └── MainWindow (windows/main_window.py)
        ├── StatusPanel (widgets/status_panel.py)
        ├── MetricsDisplay (widgets/metrics_display.py)
        ├── LogViewer (windows/log_viewer.py)
        │   └── LogWatcher (QThread)
        ├── SettingsDialog (windows/settings_dialog.py)
        │   └── ConfigManager (controllers/config_manager.py)
        ├── WorkerController (controllers/worker_controller.py)
        │   └── MetricsWorker (QThread)
        ├── TrayIconManager (utils/tray_icon.py)
        └── AppConfig (utils/app_config.py)
```

## 🎯 Common Tasks Reference

### Task: Add New Metric Display
1. Edit: `gui/widgets/status_panel.py` or `metrics_display.py`
2. Add UI element in `init_ui()`
3. Update `update_status()` or `update_metrics()` slot

### Task: Add New Configuration Option
1. Edit: `gui/windows/settings_dialog.py`
2. Add form field in appropriate tab
3. Update `build_config_from_forms()`
4. Update `load_configuration()`

### Task: Add New Log Source
1. Edit: `gui/windows/log_viewer.py`
2. Add to `log_file_combo` items in `init_ui()`
3. Ensure log file exists in `logs/` directory

### Task: Add New Menu Item
1. Edit: `gui/windows/main_window.py`
2. Add to `create_menu_bar()`
3. Create action and connect to slot

### Task: Add New Worker API Endpoint
1. Edit: `gui/controllers/worker_controller.py`
2. Add method to call endpoint
3. Emit signal with results
4. Connect to UI slot in `main_window.py`

## 📚 Documentation Guide

### For Users:
- **Start here**: `QUICK_START_GUI.md`
- **Complete guide**: `gui/README.md`
- **Troubleshooting**: `gui/README.md` → Troubleshooting section

### For Developers:
- **Architecture**: `GUI_IMPLEMENTATION.md`
- **Code structure**: This file
- **Dependencies**: `requirements-gui.txt`
- **API integration**: `gui/controllers/worker_controller.py`

### For Designers:
- **Icon guidelines**: `gui/resources/icons/README.md`
- **UI layout**: `gui/windows/main_window.py`
- **Widget design**: `gui/widgets/` directory

## 🔧 Development Workflow

### 1. Setup Development Environment
```powershell
# Install dependencies
.\venv\Scripts\pip.exe install -r requirements-gui.txt

# Launch in debug mode
.\launch-gui.ps1 -Debug
```

### 2. Make Changes
- Edit files in `gui/` directory
- Follow PySide6 signal-slot pattern
- Use QThread for background tasks
- Document with docstrings

### 3. Test Changes
- Launch GUI: `.\launch-gui.ps1 -Debug`
- Test UI interactions
- Verify thread safety
- Check error handling

### 4. Update Documentation
- Update relevant README sections
- Add comments to new code
- Update this index if structure changes

## 🚀 Deployment

### Package Contents
```
gui/                    # Complete GUI application
requirements-gui.txt    # Dependencies
launch-gui.ps1         # Launcher
GUI_IMPLEMENTATION.md   # Technical docs
QUICK_START_GUI.md     # User guide
```

### Installation on Windows
1. Copy `gui/` folder to `C:\AutoBot\NPU\`
2. Copy launcher scripts to `C:\AutoBot\NPU\`
3. Install dependencies: `.\venv\Scripts\pip.exe install -r requirements-gui.txt`
4. Launch: `.\launch-gui.ps1`

## 📞 Support Resources

- **Code Issues**: Check inline comments and docstrings
- **UI Issues**: See `gui/windows/` files
- **API Issues**: Check `gui/controllers/worker_controller.py`
- **Config Issues**: See `gui/controllers/config_manager.py`
- **General Help**: `gui/README.md`

---

**File Index** | AutoBot NPU Worker GUI v1.0.0 | 2025-10-04
