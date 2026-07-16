# Demo script

1. Start the backend from `services/backend`:

   ```powershell
   .\\.venv\\Scripts\\alembic.exe upgrade head
   .\\.venv\\Scripts\\python.exe -m uvicorn rafeeq_backend.main:app --host 0.0.0.0 --port 8000
   ```

2. Build the mobile web client from `apps/mobile`:

   ```powershell
   C:\\flutter\\bin\\flutter.bat build web --no-wasm-dry-run
   python -m http.server 8080 --bind 0.0.0.0 --directory build\\web
   ```

3. On an iPhone connected to the same Wi-Fi, open `http://10.78.178.45:8080` in Safari.
4. Create a caregiver account and patient profile.
5. Add a medication reminder, then mark its occurrence complete.
6. Open Settings → Activities, add an activity, start it, and complete it.
7. Open Settings → Memory support, add a category and a text memory.
8. Open Emergencies, pair the simulator, trigger SOS, acknowledge it, and resolve it with a note.
9. Trigger a possible fall. Test both “I am okay” and “no response” outcomes.
   For the trained laptop-camera path, run `edge\robot\.venv\Scripts\rafeeq-fall-demo.exe`,
   remain fully visible until the preview says `ML READY`, and **do not perform a real fall**.
   Lower yourself safely sideways onto a sofa or exercise mat, then test `S` (safe), `H` (help),
   and the 20-second no-response timeout. Use `F` only to isolate the verification pipeline from
   model inference.
10. Register a separate doctor account, invite its email from the caregiver’s Doctor screen, then log in as the doctor and add a shared note.
11. Review the caregiver and doctor reports.

The simulation buttons are explicitly development-only and do not represent automatic calls to emergency services.
