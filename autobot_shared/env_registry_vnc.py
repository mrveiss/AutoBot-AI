# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""VNC desktop AUTOBOT_* environment variable registrations (#22144, #22145).

Split out of ``env_registry_backend_services.py`` so that file stays under its size limit.
Registration contract (import side effect, ordering): see ``env_registry`` (#16415).
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_VNC_UPSTREAM_SCHEME",
        type=str,
        default="https",
        description=(
            "Scheme of the upstream noVNC/websockify endpoints the backend probes and proxies "
            "(api/vnc_proxy.py). websockify runs --ssl-only, so the default is https; the WebSocket scheme "
            "follows (https->wss, http->ws)."
        ),
        component="desktop",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_VNC_OBSERVATION_TIMEOUT_S",
        type=int,
        default=1,
        description=(
            "Seconds the VNC proxy waits when it posts an observation event to the MCP bridge "
            "(api/vnc_proxy.py). Fire-and-forget, so short."
        ),
        component="desktop",
        range=(1, 60),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_VNC_STATUS_PROBE_TIMEOUT_S",
        type=int,
        default=5,
        description=(
            "Seconds the VNC proxy waits for the upstream noVNC page when reporting status (api/vnc_proxy.py)."
        ),
        component="desktop",
        range=(1, 120),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_VNC_CLIENT_CONNECT_TIMEOUT_S",
        type=int,
        default=10,
        description=(
            "Seconds to open and authenticate an RFB connection to a /secrets host for a chat Desktop control "
            "(api/vnc_rfb_client.py)."
        ),
        component="desktop",
        range=(1, 120),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_VNC_CLIENT_FRAME_TIMEOUT_S",
        type=int,
        default=15,
        description=(
            "Seconds to wait for the framebuffer after a screenshot request to a /secrets host "
            "(api/vnc_rfb_client.py)."
        ),
        component="desktop",
        range=(1, 300),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_VNC_CLIENT_MAX_FRAMEBUFFER_BYTES",
        type=int,
        default=67108864,
        description=(
            "Largest framebuffer rectangle, in bytes, a screenshot read accepts before refusing "
            "(api/vnc_rfb_client.py)."
        ),
        component="desktop",
        range=(1048576, 1073741824),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_VNC_INPUT_STEP_DELAY_S",
        type=float,
        default=0.02,
        description=(
            "Seconds between synthesised input events (click press/release, drag path points) sent to a "
            "/secrets host, so the remote server applies them in order (api/vnc_host_actions.py)."
        ),
        component="desktop",
        range=(0.0, 5.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_VNC_PROXY_OWN_DESKTOP",
        type=bool,
        default=False,
        description=(
            "Serve the noVNC page, assets and websocket proxy for AutoBot's own desktop (vnc type "
            "'desktop') through api/vnc_proxy.py. Off by default: the chat app reaches only /secrets "
            "hosts. Enable only for agent-desktop observation; /status is always served."
        ),
        component="desktop",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_VNC_CLIENT_MAX_TEXT_BYTES",
        type=int,
        default=1048576,
        description=(
            "Largest desktop name or server clipboard text, in bytes, an RFB connection to a /secrets host "
            "accepts before refusing it (api/vnc_rfb_client.py)."
        ),
        component="desktop",
        range=(1024, 67108864),
    )
)
