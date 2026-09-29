# AutoBot TTS Worker

Text-to-speech microservice using [Kani-TTS-2](https://huggingface.co/liquid-ai/kani-tts-2)
(400M params, Apache 2.0). Runs natively on the NPU VM (172.16.168.22) via systemd.

## Architecture

```
autobot-backend POST /api/voice/synthesize
    └─► TTS Worker POST /tts/synthesize (NPU node, port 8083)
            └─► Kani-TTS-2 (CPU mode, ~3GB RAM)
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Service health + model status |
| POST | /tts/synthesize | Text → WAV audio (form: `text`) |
| POST | /tts/clone-voice | Zero-shot voice cloning (form: `text` + `reference_audio` file) |

## Deployment

Managed by Ansible role `tts-worker`. Deploy via:

```bash
cd autobot-slm-backend/ansible
ansible-playbook playbooks/deploy-full.yml --tags tts-worker
```

## Configuration (environment variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `TTS_HOST` | `0.0.0.0` | Bind address |
| `TTS_PORT` | `8083` | Listen port, rendered from `tts_port` in the tts-worker role, which is authoritative. 8082 is WSL2/Hyper-V reserved on the NPU host class (#3431, incident #3464). |
| `TTS_MODEL_ID` | `liquid-ai/kani-tts-2` | HuggingFace model ID |
| `TTS_DEVICE` | `cpu` | Inference device (`cpu`, `cuda`, `mps`) |
| `TTS_MODELS_DIR` | `/var/lib/autobot/models/tts` | Model cache directory |
| `HF_TOKEN` | *(unset)* | HuggingFace auth token — required for gated models. Set via `vault_hf_token` in Ansible vault. |

## Resource Requirements

- RAM: ~3 GB (CPU inference)
- Disk: ~3 GB (model weights cached on first startup)
- CPU: multi-core recommended (inference is CPU-bound)

## Issue

Implements GitHub issue #928 (Phase 19: Voice & Audio).
