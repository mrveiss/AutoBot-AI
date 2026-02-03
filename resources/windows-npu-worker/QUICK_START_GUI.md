# Quick Start: AutoBot NPU Worker GUI

## 📋 Prerequisites

- Windows NPU Worker installed (see `README.md`)
- Python virtual environment set up (`venv/` directory exists)
- NPU worker configuration (`config/npu_worker.yaml`)

## 🚀 Launch the GUI

### Method 1: PowerShell (Recommended)

```powershell
.\launch-gui.ps1
```

**With debug output:**
```powershell
.\launch-gui.ps1 -Debug
```

**Force reinstall dependencies:**
```powershell
.\launch-gui.ps1 -InstallDeps
```

### Method 2: Batch File

```batch
launch-gui.bat
```

### Method 3: Direct Python

```powershell
.\venv\Scripts\python.exe .\gui\main.py
```

## 📊 First Steps

1. **Launch GUI** - Use any method above
2. **Start Service** - Click the "▶ Start" button
3. **View Dashboard** - See real-time NPU metrics and task statistics
4. **Check Logs** - Switch to "Logs" tab for service output
5. **Configure Settings** - File → Settings to customize

## 🎛️ Main Features

### Dashboard Tab
- **NPU Status**: Utilization, temperature, power usage
- **Task Statistics**: Completed/failed tasks, response times
- **Loaded Models**: Currently loaded AI models
- **Performance Metrics**: Historical data and cache stats

### Logs Tab
- **Real-time Streaming**: Live log updates
- **Multiple Sources**: app.log, service.log, error.log
- **Export**: Save logs to file
- **Auto-scroll**: Automatic scroll to latest entries

### Settings (File → Settings)
- **YAML Editor**: Direct configuration editing
- **Service Settings**: Host, port, workers
- **NPU Configuration**: Precision, batch size, optimization
- **Logging**: Log level, directory, size limits

## 🔧 Service Control

### Start Service
- Click "▶ Start" button
- Or: Service → Start Service
- Or: Right-click tray icon → Start Service

### Stop Service
- Click "⏹ Stop" button
- Or: Service → Stop Service
- Or: Right-click tray icon → Stop Service

### Restart Service
- Click "🔄 Restart" button
- Or: Service → Restart Service
- Automatically prompted after settings changes

## 💡 System Tray

The application runs in the system tray for background operation:

**Double-click tray icon**: Show/hide dashboard

**Right-click tray icon**:
- Show Dashboard
- Start Service
- Stop Service
- Exit

## ⌨️ Keyboard Shortcuts

- **Ctrl+S**: Open Settings
- **Ctrl+Q**: Quit Application
- **F5**: Refresh Logs (when in Logs tab)

## 🔍 Troubleshooting

### GUI Won't Start

```powershell
# Check PySide6 installation
.\venv\Scripts\pip.exe show PySide6

# Reinstall if needed
.\venv\Scripts\pip.exe install --force-reinstall PySide6
```

### Service Won't Start

1. Check logs in dashboard "Logs" tab
2. Verify `app\npu_worker.py` exists
3. Ensure port 8082 is not in use

### No Metrics Displayed

1. Verify service is running (green status)
2. Check `http://localhost:8082/health` in browser
3. Ensure firewall allows port 8082

### Tray Icon Missing

1. Check Windows notification area settings
2. Enable "Show icons" for the application
3. Restart the GUI

## 📁 GUI File Structure

```
gui/
├── main.py                  # Application entry point
├── windows/                 # Main windows
│   ├── main_window.py      # Dashboard
│   ├── settings_dialog.py  # Settings
│   └── log_viewer.py       # Log viewer
├── widgets/                 # Reusable components
│   ├── status_panel.py     # Status display
│   └── metrics_display.py  # Metrics charts
├── controllers/             # Business logic
│   ├── worker_controller.py # Worker management
│   └── config_manager.py    # Configuration
└── utils/                   # Utilities
    ├── app_config.py       # App config
    └── tray_icon.py        # Tray icon
```

## 🎯 Common Tasks

### Change NPU Settings

1. File → Settings
2. Go to "NPU Configuration" tab
3. Adjust precision, batch size, streams, threads
4. Click "Save"
5. Restart service when prompted

### Export Logs

1. Go to "Logs" tab
2. Select log file (app.log, service.log, error.log)
3. Click "Export..." button
4. Choose location and filename
5. Click "Save"

### Backup Configuration

Configurations are automatically backed up when saved:
- Location: `config/backups/`
- Format: `npu_worker_YYYYMMDD_HHMMSS.yaml`
- Retention: Last 10 backups kept

## 📚 Documentation

- **GUI Documentation**: `gui/README.md`
- **Implementation Details**: `GUI_IMPLEMENTATION.md`
- **NPU Worker Guide**: `README.md`
- **Deployment Info**: `DEPLOYMENT_SUMMARY.md`

## 🆘 Getting Help

1. Check `gui/README.md` for detailed documentation
2. Review logs in the "Logs" tab
3. See `GUI_IMPLEMENTATION.md` for technical details
4. Consult AutoBot docs: `/home/kali/Desktop/AutoBot/docs/`

## ✅ Verification Checklist

- [ ] GUI launches without errors
- [ ] Service starts successfully
- [ ] Dashboard shows real-time metrics
- [ ] NPU status displays correctly
- [ ] Logs stream in real-time
- [ ] Settings can be saved
- [ ] System tray icon appears
- [ ] Start/stop controls work

---

**Quick Start Guide** | AutoBot NPU Worker GUI v1.0.0 | Windows 10/11
