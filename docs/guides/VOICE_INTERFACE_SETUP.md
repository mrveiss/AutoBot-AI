# Voice Interface Setup Guide

## Overview

The AutoBot voice interface is an optional component that provides speech recognition and text-to-speech capabilities. It requires system-level audio libraries and is separated from core dependencies to ensure the main application works in all environments.

## Quick Setup

### 1. Core Application (Always Works)
```bash
# Install main dependencies (no voice support)
pip install -r requirements.txt
```

### 2. Add Voice Support (Optional)
```bash
# Install voice interface dependencies
pip install -r requirements-voice.txt
```

## System Requirements

### Linux (Ubuntu/Debian)
```bash
# Install system audio libraries
sudo apt-get update
sudo apt-get install portaudio19-dev python3-pyaudio
sudo apt-get install espeak espeak-data libespeak1 libespeak-dev
sudo apt-get install flac

# Then install Python dependencies
pip install -r requirements-voice.txt
```

### macOS
```bash
# Install system audio libraries
brew install portaudio
brew install espeak

# Then install Python dependencies
pip install -r requirements-voice.txt
```

### Windows
```bash
# PyAudio wheels are available for Windows
pip install -r requirements-voice.txt

# May need to install additional audio drivers
```

## Dependencies Included

The `requirements-voice.txt` includes:
- `speechrecognition==3.10.0` - Speech-to-text
- `pydub==0.25.1` - Audio processing
- `pyaudio==0.2.11` - Audio I/O (requires system libraries)
- `gtts==2.3.1` - Google Text-to-Speech

## Graceful Degradation

The voice interface is designed to work gracefully when dependencies are missing:

### With Voice Dependencies
- ✅ Full speech recognition
- ✅ Text-to-speech output
- ✅ Voice commands
- ✅ Audio processing

### Without Voice Dependencies
- ✅ Main AutoBot functionality works normally
- ✅ Chat interface remains functional
- ✅ All other features available
- ⚠️ Voice interface shows "not available" message
- ⚠️ Voice-related API endpoints return graceful errors

## Testing Voice Setup

### Check if Voice is Available
```python
from src.voice_interface import VoiceInterface, SPEECH_RECOGNITION_AVAILABLE

vi = VoiceInterface()
if SPEECH_RECOGNITION_AVAILABLE:
    print("✅ Voice interface is available")
else:
    print("❌ Voice interface not available - install requirements-voice.txt")
```

### Test Speech Recognition
```bash
# Through the API
curl -X POST http://localhost:8001/api/voice/recognize

# Should return either recognition result or graceful error
```

## CI/CD Considerations

### GitHub Actions
```yaml
# In your GitHub workflow
- name: Install core dependencies
  run: pip install -r requirements.txt

# Optional voice setup (may fail in CI)
- name: Install voice dependencies (optional)
  run: pip install -r requirements-voice.txt || echo "Voice dependencies skipped"
  continue-on-error: true
```

### Docker
```dockerfile
# Core installation (always works)
RUN pip install -r requirements.txt

# Optional voice support
RUN apt-get update && apt-get install -y portaudio19-dev || true
RUN pip install -r requirements-voice.txt || echo "Voice dependencies skipped"
```

## Troubleshooting

### Common Issues

1. **pyaudio installation fails**
   ```bash
   # On Ubuntu/Debian
   sudo apt-get install portaudio19-dev python3-pyaudio

   # On macOS
   brew install portaudio
   export LDFLAGS="-L$(brew --prefix portaudio)/lib"
   export CPPFLAGS="-I$(brew --prefix portaudio)/include"
   pip install pyaudio
   ```

2. **No microphone detected**
   - Check system audio settings
   - Ensure microphone permissions are granted
   - Test with `arecord -l` (Linux) or system audio preferences

3. **TTS not working**
   ```bash
   # Install system TTS engines
   sudo apt-get install espeak  # Linux
   brew install espeak         # macOS
   ```

### Verification Commands
```bash
# Check if pyaudio can access microphone
python -c "import pyaudio; p = pyaudio.PyAudio(); print(f'Audio devices: {p.get_device_count()}')"

# Check speech recognition
python -c "import speech_recognition as sr; print('Speech recognition available')"

# Check TTS
python -c "import gtts; print('Google TTS available')"
```

## Integration with AutoBot

The voice interface integrates seamlessly with the main AutoBot application:

### API Endpoints
- `POST /api/voice/recognize` - Convert speech to text
- `POST /api/voice/synthesize` - Convert text to speech
- `GET /api/voice/status` - Check voice interface availability

### Frontend Integration
The Vue.js frontend automatically detects voice availability and shows/hides voice controls accordingly.

### Configuration
Voice settings are configured in `config/config.yaml`:
```yaml
voice_interface:
  enabled: true
  recognition:
    language: "en-US"
    timeout: 5
  synthesis:
    language: "en"
    speed: 150
```

## Conclusion

The separated voice dependencies ensure that:
1. **Core AutoBot works everywhere** - No audio library requirements for main functionality
2. **Optional enhancement** - Voice features when system supports it
3. **CI/CD friendly** - Build pipelines won't fail due to audio library issues
4. **Production ready** - Graceful degradation in server environments
