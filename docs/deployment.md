# RAFEEQ deployment from a Windows laptop

This setup keeps the heavy backend services online and leaves the Flutter web
app on your laptop during the prototype:

- Cloud/VPS server: FastAPI backend, PostgreSQL, Redis, Mosquitto MQTT.
- Raspberry Pi: robot voice, speaker, camera, fall detection.
- Laptop: Flutter web app opened in Chrome.

For London testing, use a VPS region in London when possible.

## 1. Create the server

Create an Ubuntu 24.04 VPS with at least:

- 2 GB RAM for basic demos.
- 4 GB RAM if several people will test at the same time.
- Public IPv4 address.
- SSH access from your laptop.

Keep the server IP. In the commands below it is called `YOUR_SERVER_IP`.

## 2. Prepare production secrets on the laptop

From the repository root:

```powershell
cd C:\RAFFEQ
.\scripts\prepare_deployment_env.ps1 -ServerHost YOUR_SERVER_IP
```

This creates `.env.production`. It is ignored by Git and must stay private.

If you want the backend/robot to use OpenAI, pass the key while generating the
file:

```powershell
.\scripts\prepare_deployment_env.ps1 -ServerHost YOUR_SERVER_IP -OpenAiApiKey "YOUR_OPENAI_API_KEY"
```

Do not put the OpenAI key in Flutter.

## 3. Deploy from the laptop

```powershell
.\scripts\deploy_to_server.ps1 -ServerHost YOUR_SERVER_IP
```

The script will:

1. Install Docker and Git on the server.
2. Clone `https://github.com/oly4/RAFEEQ.git` into `/opt/rafeeq`.
3. Upload `.env.production`.
4. Start PostgreSQL, Redis, Mosquitto, and the backend.

## 4. Check the backend

Open:

```text
http://YOUR_SERVER_IP:8000/health/ready
```

Expected result:

```json
{"status":"ready","environment":"production"}
```

## 5. Run the Flutter app from the laptop

```powershell
.\scripts\run_app_windows.ps1 -BackendHost YOUR_SERVER_IP -RemoteBackend
```

Then open:

```text
http://127.0.0.1:8080
```

Demo accounts:

```text
Family: caregiver@demo.rafeeq.app / Rafeeq-Test-2026!
Doctor: doctor@demo.rafeeq.app / Rafeeq-Test-2026!
```

## 6. Point the Raspberry Pi robot to the cloud backend

On the Raspberry Pi, set:

```env
BACKEND_BASE_URL=http://YOUR_SERVER_IP:8000
MQTT_HOST=YOUR_SERVER_IP
MQTT_PORT=1883
```

Then restart RAFEEQ services on the Pi.

## Important notes

- This first deployment uses HTTP for speed while prototyping.
- For public users, add a domain and HTTPS before sharing the app widely.
- Browser microphone/camera features usually require HTTPS unless the app is
  opened from localhost. The robot voice/camera on Raspberry Pi does not need
  browser HTTPS because it uses the Pi hardware directly.
- Keep `.env.production`, `.env`, `.env.robot`, and API keys out of Git.
