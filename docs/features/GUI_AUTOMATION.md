# GUI Automation and Computer Vision

**Status:** ✅ Production Ready
**Version:** 1.0.0
**Date:** 2025-11-16
**Issue:** #52 - Enhanced Computer Vision for GUI Automation
**Author:** mrveiss

## Overview

AutoBot's GUI Automation system provides advanced screen understanding and visual automation capabilities through computer vision, OCR, and AI-powered element recognition.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Vision API Layer                    │
│            backend/api/vision.py                     │
└─────────────────┬───────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────┐
│           Computer Vision System                     │
│        src/computer_vision_system.py                 │
├─────────────────────────────────────────────────────┤
│  ┌─────────┐  ┌─────────┐  ┌──────────────────┐   │
│  │ Screen  │  │ Template│  │    Element       │   │
│  │ Analyzer│  │ Matcher │  │   Classifier     │   │
│  └─────────┘  └─────────┘  └──────────────────┘   │
└─────────────────┬───────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────┐
│              Processing Backends                     │
├──────────┬────────────┬─────────────┬───────────────┤
│  OpenCV  │ Pytesseract│  Multimodal │   Desktop     │
│   (CV)   │   (OCR)    │  Processor  │   Streaming   │
└──────────┴────────────┴─────────────┴───────────────┘
```

## Core Components

### 1. Computer Vision System (`src/computer_vision_system.py`)

**Main Classes:**

- **ScreenAnalyzer** - Comprehensive screen state analysis
- **TemplateMatchingEngine** - Template-based element location
- **ElementClassifier** - UI element classification
- **ContextAnalyzer** - Screen context understanding

**Supported Element Types (14 types):**
- Button, Input Field, Checkbox, Radio Button
- Dropdown, Link, Image, Text, Menu
- Dialog, Window, Icon, Toolbar, Status Bar

**Supported Interactions (8 types):**
- Click, Double Click, Right Click, Drag
- Type Text, Select, Scroll, Hover

### 2. Vision REST API (`backend/api/vision.py`)

**Endpoints:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/vision/health` | GET | Service health check |
| `/api/vision/status` | GET | Service status and capabilities |
| `/api/vision/analyze` | POST | Full screen analysis |
| `/api/vision/elements` | POST | Detect UI elements |
| `/api/vision/ocr` | POST | Extract text via OCR |
| `/api/vision/automation-opportunities` | GET | Identify automation actions |
| `/api/vision/layout` | GET | Analyze screen layout |
| `/api/vision/element-types` | GET | List supported element types |
| `/api/vision/interaction-types` | GET | List supported interactions |

### 3. Desktop Streaming Manager

Provides real-time screen capture at 30 FPS via VNC integration.

## API Usage

### Health Check

```bash
curl http://localhost:8001/api/vision/health
```

Response:
```json
{
  "status": "healthy",
  "analyzer_ready": true,
  "capabilities": [
    "screen_capture",
    "element_detection",
    "ocr_text_extraction",
    "template_matching",
    "context_analysis",
    "multimodal_processing"
  ],
  "element_types_supported": ["button", "input_field", ...],
  "interaction_types_supported": ["click", "double_click", ...]
}
```

### Full Screen Analysis

```bash
curl -X POST http://localhost:8001/api/vision/analyze \
  -H "Content-Type: application/json" \
  -d '{"session_id": "user123", "include_multimodal": true}'
```

Response:
```json
{
  "timestamp": 1700000000.123,
  "ui_elements": [
    {
      "element_id": "btn_001",
      "element_type": "button",
      "bbox": {"x": 100, "y": 200, "width": 80, "height": 30},
      "center_point": [140, 215],
      "confidence": 0.95,
      "text_content": "Submit",
      "possible_interactions": ["click", "hover"]
    }
  ],
  "text_regions": [...],
  "dominant_colors": [{"color": "#ffffff", "percentage": 45.2}],
  "layout_structure": {...},
  "automation_opportunities": [...],
  "context_analysis": {...},
  "confidence_score": 0.87
}
```

### Element Detection with Filters

```bash
curl -X POST http://localhost:8001/api/vision/elements \
  -H "Content-Type: application/json" \
  -d '{
    "element_type": "button",
    "min_confidence": 0.8
  }'
```

Response:
```json
{
  "total_detected": 25,
  "filtered_count": 8,
  "elements": [
    {
      "element_id": "btn_001",
      "element_type": "button",
      "bbox": {"x": 100, "y": 200, "width": 80, "height": 30},
      "center_point": [140, 215],
      "confidence": 0.95,
      "text_content": "Submit",
      "possible_interactions": ["click", "hover"]
    }
  ],
  "filter_applied": {
    "element_type": "button",
    "min_confidence": 0.8
  }
}
```

### OCR Text Extraction

```bash
# Full screen OCR
curl -X POST http://localhost:8001/api/vision/ocr \
  -H "Content-Type: application/json" \
  -d '{}'

# Region-specific OCR
curl -X POST http://localhost:8001/api/vision/ocr \
  -H "Content-Type: application/json" \
  -d '{
    "region": {"x": 100, "y": 100, "width": 500, "height": 200}
  }'
```

### Automation Opportunities

```bash
curl http://localhost:8001/api/vision/automation-opportunities
```

Response:
```json
{
  "opportunities": [
    {
      "type": "form_submission",
      "elements_involved": ["input_001", "btn_submit"],
      "confidence": 0.92,
      "suggested_actions": ["fill_form", "click_submit"]
    }
  ],
  "total_opportunities": 3,
  "context": {...},
  "confidence": 0.89
}
```

## Python SDK Usage

```python
from src.computer_vision_system import ScreenAnalyzer

# Initialize analyzer
analyzer = ScreenAnalyzer()

# Analyze current screen
screen_state = await analyzer.analyze_current_screen(session_id="user123")

# Get all detected UI elements
for element in screen_state.ui_elements:
    print(f"Found {element.element_type.value}: {element.text_content}")
    print(f"  Location: {element.center_point}")
    print(f"  Confidence: {element.confidence}")
    print(f"  Can: {[i.value for i in element.possible_interactions]}")

# Check automation opportunities
for opportunity in screen_state.automation_opportunities:
    print(f"Automation: {opportunity['type']}")
    print(f"  Suggested: {opportunity['suggested_actions']}")

# Access layout structure
print(f"Layout: {screen_state.layout_structure}")
print(f"Context: {screen_state.context_analysis}")
```

## Integration with AutoBot Features

### 1. VNC Desktop Streaming

The vision system integrates with the VNC desktop streaming manager for real-time screen capture:

```python
from src.desktop_streaming_manager import desktop_streaming

# Screen capture happens automatically during analysis
screen_state = await analyzer.analyze_current_screen()
```

### 2. Multi-Modal Processing

Integration with AutoBot's unified multi-modal processor:

```python
# Automatically enabled in screen analysis
analyzer.enable_multimodal_analysis = True
screen_state = await analyzer.analyze_current_screen()

# Access multi-modal insights
if screen_state.multimodal_analysis:
    for insight in screen_state.multimodal_analysis:
        print(f"AI Insight: {insight}")
```

### 3. Task Execution Tracking

Screen analysis integrates with task tracking:

```python
from src.task_execution_tracker import task_tracker

# Analysis automatically tracked
async with task_tracker.track_task("Screen Analysis", ...):
    screen_state = await analyzer.analyze_current_screen()
```

## Performance Characteristics

| Operation | Typical Latency | Notes |
|-----------|----------------|-------|
| Full Screen Analysis | 200-500ms | Includes all processors |
| Element Detection Only | 100-200ms | CV operations only |
| OCR Extraction | 150-300ms | Pytesseract processing |
| Template Matching | 50-150ms | Per template |

## Configuration

### Environment Variables

```bash
# Vision Configuration
VISION_ENABLE_MULTIMODAL=true
VISION_OCR_LANG=eng
VISION_CONFIDENCE_THRESHOLD=0.5
VISION_CACHE_SIZE=5
```

### Performance Tuning

```python
# Adjust cache size for recent screenshots
analyzer.cache_size = 10

# Disable multi-modal for faster processing
analyzer.enable_multimodal_analysis = False

# Set minimum confidence threshold
request = ElementDetectionRequest(min_confidence=0.8)
```

## Error Handling

The API uses standardized error responses:

```json
{
  "error": "Screen analysis failed",
  "detail": "Failed to capture screenshot: Desktop not available",
  "error_code": "VISION_001"
}
```

Common error codes:
- `VISION_001` - Screenshot capture failed
- `VISION_002` - Element detection failed
- `VISION_003` - OCR extraction failed
- `VISION_004` - Template matching failed

## Security Considerations

1. **Screen Content Privacy**: Screen captures may contain sensitive information
2. **Session Isolation**: Each session has isolated analysis context
3. **Rate Limiting**: API endpoints should have rate limits in production
4. **Input Validation**: All inputs validated via Pydantic models

## Testing

```bash
# Run vision API tests
python -m pytest tests/ -k "vision" -v

# Test specific endpoint
curl http://localhost:8001/api/vision/health

# Verify element detection
curl -X POST http://localhost:8001/api/vision/elements -H "Content-Type: application/json" -d '{}'
```

## Dependencies

- **OpenCV** (`cv2`) - Image processing
- **Pytesseract** - OCR text extraction
- **NumPy** - Array operations
- **Pillow** (PIL) - Image manipulation
- **FastAPI** - REST API framework
- **Pydantic** - Data validation

## Future Enhancements

1. **Advanced Object Detection**: YOLO/SSD models for better element recognition
2. **Semantic UI Understanding**: AI-powered understanding of UI semantics
3. **Action Validation**: Verify element states after interactions
4. **Custom Template Training**: Train custom templates for specific applications
5. **WebSocket Streaming**: Real-time element detection updates

## Related Documentation

- [Desktop Streaming Setup](../setup/DESKTOP_STREAMING.md)
- [VNC Configuration](../setup/VNC_SETUP.md)
- [Multi-Modal Processing](MULTIMODAL_PROCESSING.md)
- [API Documentation](../api/COMPREHENSIVE_API_DOCUMENTATION.md)

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-11-16 | Initial documentation (Issue #52) |

## References

- **GitHub Issue:** #52 - Enhanced Computer Vision for GUI Automation
- **Core Implementation:** `src/computer_vision_system.py`
- **API Endpoint:** `backend/api/vision.py`
- **Related Systems:** Desktop Streaming, Multi-Modal Processor
