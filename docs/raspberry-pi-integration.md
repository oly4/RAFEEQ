# RAFEEQ Raspberry Pi Integration

Recommended prototype setup:

- Raspberry Pi runs the backend, robot voice process, and camera/fall detector.
- Laptop runs Flutter/web UI during development.
- The Flutter app connects to the Raspberry Pi backend over the local network.

Example Raspberry Pi backend address:

```text
http://172.20.10.2:8000
```

## Run the Flutter app from Windows against the Pi backend

From `C:\RAFFEQ`:

```powershell
.\scripts\run_app_windows.ps1 -BackendHost 172.20.10.2 -RemoteBackend
```

This builds and serves the Flutter web app locally, but compiles it with:

```text
API_BASE_URL=http://172.20.10.2:8000/api/v1
WS_BASE_URL=ws://172.20.10.2:8000
```

If you want direct Chrome hot reload instead of the static web server:

```powershell
.\scripts\run_app_chrome_windows.ps1 -BackendHost 172.20.10.2 -RemoteBackend
```

## Raspberry Pi side

Do not install Flutter on the Pi unless you specifically want the Pi to host the
web app. Flutter is large and slow on Raspberry Pi.

The Pi should run:

```bash
cd /opt/rafeeq
services/backend/.venv/bin/python -m uvicorn rafeeq_backend.main:app --host 0.0.0.0 --port 8000
```

Robot voice:

```bash
cd /opt/rafeeq
edge/robot/.venv/bin/rafeeq-robot
```

Camera/fall detection:

```bash
cd /opt/rafeeq
edge/robot/.venv/bin/rafeeq-fall-demo --camera-index 0 --detector heuristic --speaker openai --voice-verification
```

## Important

Use the Pi LAN IP in the Flutter build, not `127.0.0.1`.

`127.0.0.1` means "this same device", so from the laptop or phone it will not
reach the Raspberry Pi backend.
