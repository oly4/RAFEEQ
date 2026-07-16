# Security and privacy

RAFEEQ minimizes sensitive collection. Raw camera and microphone streams remain local by default. Secrets are injected through the environment and excluded from Git. Production requires TLS, authenticated MQTT with per-device credentials, password hashing, rotating refresh tokens, relation-based authorization, audit logging, rate limiting, and privacy-safe push text. Legal and medical-device regulatory review remains pending; this prototype makes no certification claim.

The mobile camera test is an explicit, user-started live preview. Audio is disabled, and the test does not record, persist, analyze, or upload frames. Browser camera permission requires HTTPS. The local Apple-device demo uses a development-only CA and certificates stored under the ignored `.run/tls` directory. The development CA must never be reused for production.

The laptop fall-detection demo processes webcam frames in memory with a local MediaPipe pose
model and a trained temporal classifier. It stores only structured possible-fall and verification
events; it does not save or upload raw frames. The third-party classifier is pinned to a reviewed
commit and its SHA-256 digest is checked before Joblib deserialization. Its staged-fall training
data and webcam domain shift mean it must not be treated as a validated safety or medical system.
