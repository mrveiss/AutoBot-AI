# AutoBot NPU Worker GUI

Windows desktop application for managing the NPU worker service with real-time monitoring and control.

## Features

### 🎛️ Dashboard
- **Real-time NPU Metrics**: Utilization, temperature, power usage
- **Task Statistics**: Completed tasks, failed tasks, average response time
- **Model Management**: View loaded models and their details
- **Performance History**: Track metrics over time

### 🔧 Service Control
- **Start/Stop/Restart**: Full service lifecycle management
- **System Tray Integration**: Run in background with quick access
- **Status Monitoring**: Real-time service health checks

### 📊 Advanced Monitoring
- **Live Log Viewer**: Real-time log streaming with filtering
- **Metrics History**: Historical performance data
- **Cache Statistics**: Embedding cache hit rate and efficiency
- **Model Details**: Size, precision, last used, device assignment

### ⚙️ Configuration
- **YAML Editor**: Direct configuration editing with validation
- **Form-based Settings**: Guided configuration for common settings
- **Backup Management**: Automatic configuration backups
- **Service Settings**: Host, port, workers, backend, Redis
- **NPU Settings**: Precision, batch size, streams, threads
- **Logging Settings**: Log level, directory, size limits

## Installation

### Prerequisites
- Windows 10/11 (64-bit)
- Python 3.10+ with PySide6
- NPU worker already installed (see parent README.md)

### Install GUI Dependencies

```powershell
# Navigate to NPU worker directory
cd C:\AutoBot\NPU

# Install GUI requirements
.\venv\Scripts\pip.exe install -r requirements-gui.txt
```

## Usage

### Starting the GUI

```powershell
# Option 1: Using Python directly
.\venv\Scripts\python.exe .\gui\main.py

# Option 2: Create desktop shortcut (recommended)
# Right-click on gui\main.py -> Send to -> Desktop (create shortcut)
# Edit shortcut target to: C:\AutoBot\NPU\venv\Scripts\pythonw.exe C:\AutoBot\NPU\gui\main.py
```

### First Launch

1. **Start the GUI** - The application opens with the dashboard
2. **Start the Service** - Click "▶ Start" button
3. **Monitor Status** - View real-time NPU metrics and task statistics
4. **Configure Settings** - File → Settings to customize configuration
5. **View Logs** - Switch to "Logs" tab for real-time log viewing

### System Tray

The application minimizes to the system tray for background operation:
- **Double-click tray icon**: Show/hide dashboard
- **Right-click tray icon**: Quick access menu
  - Show Dashboard
  - Start/Stop Service
  - Exit

### Configuration

**Settings Dialog** (File → Settings):

1. **YAML Editor Tab**: Direct YAML editing with validation
2. **Service Tab**: Host, port, workers, backend, Redis settings
3. **NPU Configuration Tab**: Precision, batch size, streams, threads
4. **Logging Tab**: Log level, directory, size, backup count

**Applying Changes**:
- **Save**: Save and close dialog
- **Apply**: Save without closing
- **Cancel**: Discard changes

If service is running, you'll be prompted to restart for changes to take effect.

## GUI Components

### Main Window (`main_window.py`)
- Central dashboard with tabbed interface
- Service control buttons
- System tray integration
- Menu bar with File, Service, Help menus

### Settings Dialog (`settings_dialog.py`)
- Tabbed settings interface
- YAML editor with validation
- Form-based configuration
- Backup management

### Log Viewer (`log_viewer.py`)
- Real-time log streaming
- Log file selection (app.log, service.log, error.log)
- Auto-scroll support
- Export functionality

### Status Panel (`status_panel.py`)
- NPU status display
- Task statistics
- Loaded models list
- Real-time metrics

### Metrics Display (`metrics_display.py`)
- Performance summary
- Cache statistics
- Model details table
- Metrics history table

### Controllers

**Worker Controller** (`worker_controller.py`):
- Process management (start/stop/restart)
- Health monitoring
- Metrics fetching via API
- Background thread for non-blocking operations

**Config Manager** (`config_manager.py`):
- YAML configuration loading/saving
- Validation
- Backup management
- Default configuration

## Architecture

### Threading Model

The GUI uses Qt's threading system for non-blocking operations:

```python
# Main Thread (UI)
└── QMainWindow (main_window.py)
    ├── Status updates (QTimer)
    ├── Metrics updates (QTimer)
    └── User interactions

# Background Threads
├── MetricsWorker (QThread)
│   └── API calls to /health and /stats
├── LogWatcher (QThread)
│   └── File monitoring for log updates
└── Worker Process
    └── NPU worker service (subprocess)
```

### Signal-Slot Communication

Thread-safe communication using Qt signals and slots:

```python
# Controller → UI
worker_controller.status_changed.connect(main_window.on_status_changed)
worker_controller.metrics_updated.connect(main_window.on_metrics_updated)
worker_controller.error_occurred.connect(main_window.on_error)

# UI → Controller
start_btn.clicked.connect(worker_controller.start_worker)
stop_btn.clicked.connect(worker_controller.stop_worker)
```

### API Integration

The GUI communicates with the NPU worker via REST API:

- **GET** `/health` - Service health and metrics
- **GET** `/stats` - Detailed statistics
- All API calls made in background threads
- Automatic error handling and retry logic

## Development

### Project Structure

```
gui/
├── main.py                  # Application entry point
├── windows/                 # Main windows
│   ├── main_window.py      # Dashboard window
│   ├── settings_dialog.py  # Settings dialog
│   └── log_viewer.py       # Log viewer widget
├── widgets/                 # Reusable widgets
│   ├── status_panel.py     # Status display
│   └── metrics_display.py  # Metrics visualization
├── controllers/             # Business logic
│   ├── worker_controller.py # Worker process control
│   └── config_manager.py    # Configuration management
├── utils/                   # Utilities
│   ├── app_config.py       # App configuration
│   └── tray_icon.py        # System tray helper
└── resources/               # Resources
    └── icons/              # Application icons
```

### Adding New Features

1. **New Widget**: Add to `gui/widgets/`
2. **New Window**: Add to `gui/windows/`
3. **New Controller**: Add to `gui/controllers/`
4. **Connect Signals**: Use Qt signal-slot pattern
5. **Background Tasks**: Use QThread for non-blocking operations

### Debugging

Enable debug logging in main.py:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Keyboard Shortcuts

- **Ctrl+S**: Open Settings
- **Ctrl+Q**: Quit Application
- **F5**: Refresh Logs (when in Logs tab)

## Troubleshooting

### GUI Won't Start

**Issue**: Application doesn't launch
**Solution**:
```powershell
# Check PySide6 installation
.\venv\Scripts\pip.exe show PySide6

# Reinstall if needed
.\venv\Scripts\pip.exe install --force-reinstall PySide6
```

### Service Control Not Working

**Issue**: Start/Stop buttons don't work
**Solution**:
- Verify worker script exists: `app\npu_worker.py`
- Check Python executable: `venv\Scripts\python.exe`
- View logs for error details

### Metrics Not Updating

**Issue**: Dashboard shows no metrics
**Solution**:
- Ensure service is running (green status indicator)
- Check API is accessible: `curl http://localhost:8082/health`
- Verify port 8082 is not blocked by firewall

### System Tray Icon Missing

**Issue**: No tray icon visible
**Solution**:
- Check Windows notification area settings
- Ensure "Show icons" is enabled for the application
- Restart the GUI application

## Windows 11 Integration

The GUI follows Windows 11 design guidelines:

- **Fluent Design**: Modern, clean interface
- **Dark/Light Theme**: Automatic theme detection
- **High DPI**: Proper scaling for high-resolution displays
- **System Tray**: Native Windows tray integration
- **Notifications**: Windows notification system

## Performance

- **Low Resource Usage**: ~50-100MB RAM
- **Non-blocking UI**: All I/O in background threads
- **Efficient Updates**: Timer-based polling (2s status, 5s metrics)
- **Smart Caching**: Metrics history limited to 100 entries

## Security

- **Local Only**: No external network access
- **Safe Defaults**: Secure default configuration
- **Backup Protection**: Automatic config backups before changes
- **Process Isolation**: Worker runs in separate process

## Future Enhancements

Planned features for future releases:

- [ ] Performance charts (line graphs for metrics)
- [ ] Model management (load/unload models from GUI)
- [ ] Benchmark execution from GUI
- [ ] Export metrics to CSV
- [ ] Custom themes
- [ ] Notification preferences
- [ ] Multiple worker support
- [ ] Remote worker management

## License

This GUI application is part of the AutoBot NPU Worker package.
See LICENSE.txt for details.

## Support

For issues or questions:
1. Check logs in `logs/` directory
2. Review AutoBot documentation: `/home/kali/Desktop/AutoBot/docs/`
3. Report issues via AutoBot issue tracker

---

**Version**: 1.0.0
**Platform**: Windows 10/11
**Framework**: PySide6 (Qt for Python)
**Build Date**: 2025-10-04
