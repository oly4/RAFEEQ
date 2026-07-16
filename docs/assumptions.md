# Assumptions

- The laptop fall demo uses the pinned `ai-fall-detection-prototype` window classifier as a
  replaceable detection strategy. It was trained on staged LE2I footage and requires validation
  with representative RAFEEQ camera placement before any safety use.

- The supplied build specification is the source of truth and is copied to repository-root `AGENTS.md`.
- Local Safari development uses SQLite because Docker is unavailable on the current workstation. Docker explicitly uses PostgreSQL and the same Alembic migrations.
- Anonymous MQTT is allowed only in local development; authenticated per-device access is required before deployment.
- Flutter is installed at `C:\\flutter` but is not yet on the terminal `PATH`; project commands invoke it by absolute path on this workstation.
- A native iOS build still requires macOS and Xcode. The current Apple-device demonstration uses the Flutter web build in Safari.
- Development-only simulator provisioning and SOS/fall trigger endpoints are hidden when `APP_ENV` is not `development`.
- Browser tokens are kept in secure storage when the browser provides a secure context. The LAN HTTP demonstration may retain them only for the active session; production must use HTTPS.
- The Apple-device camera demonstration uses a locally trusted development CA because browser camera APIs require HTTPS. Camera preview remains entirely on the device and stops when its panel closes.
- OpenAI voice interaction uses `gpt-realtime-2.1` as the only interactive assistant
  reasoning model. Local Vosk may still be used for laptop microphone transcription,
  and the deterministic command router remains a safety fallback for offline core actions.
  RAFEEQ stores voice intents and confidence only; raw audio and full transcripts are not
  stored by default.
