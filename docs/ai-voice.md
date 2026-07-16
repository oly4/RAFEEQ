# RAFEEQ AI Voice Setup

RAFEEQ should use OpenAI voice only for interactive conversation. Medicine schedules,
SOS, fall verification, local prompts, and event logging must continue to work without
internet.

## Recommended subscription path

1. Create or open an OpenAI Platform account at `https://platform.openai.com`.
2. Add API billing/payment in the Platform billing page.
3. Create an API key for local development.
4. Store the key in `.env.robot` or your deployment secret manager, never in Flutter
   source code and never in Git.

Use `gpt-realtime-2.1-mini` for early RAFEEQ prototype testing. It is cheaper than
the full Realtime model and is enough for basic natural conversation, tool
selection, and understanding flexible patient phrases.

## Local environment

Copy `.env.example` to `.env.robot` and set:

```env
VOICE_INTERACTION_PROVIDER=vosk
VOICE_REASONING_PROVIDER=openai
SPEAKER_PROVIDER=windows
VOSK_MODEL_PATH=C:\RAFFEQ\.run\models\vosk-ar
VOSK_SAMPLE_RATE=16000
VOICE_LISTEN_SECONDS=15
OPENAI_API_KEY=sk-your-development-key
OPENAI_REALTIME_MODEL=gpt-realtime-2.1-mini
OPENAI_TEXT_MODEL=gpt-5.4-nano
OPENAI_TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe
OPENAI_TTS_MODEL=gpt-4o-mini-tts
VOICE_MAX_SESSION_SECONDS=120
VOICE_REMINDER_SNOOZE_MINUTES=10
VOICE_UPLOAD_AUDIO=false
```

`VOICE_INTERACTION_PROVIDER=vosk` keeps laptop microphone transcription local; it is
not used as the assistant brain.
`VOICE_REASONING_PROVIDER=openai` sends only the recognized transcript and synced
task statuses to GPT Realtime so it can reason and call read-only RAFEEQ tools. Do not
store API keys in Git or Flutter source code.
`SPEAKER_PROVIDER=windows` is used on the laptop demo to avoid the unstable Piper
`wave.Error: # channels not specified` failure. This is only text-to-speech output,
not the assistant reasoning model.

## Simulation commands

Run the robot simulator, synchronize routines, trigger due reminders, then test voice
intent handling with typed text:

```powershell
edge\robot\.venv\Scripts\rafeeq-robot.exe
```

Inside the robot console:

```text
sync
due
voice yes I took it
voice remind me later
voice no
voice help
voice did I finish lunch or not
voice tell me if I took my medicine or not
listen
publish
```

## Clean GPT terminal test

If voice recognition or text-to-speech feels robotic, test GPT reasoning by itself
first. This path does not use Vosk, Piper, Windows speech, Realtime audio, or the old
rule-based command matcher. It only sends typed text and synced RAFEEQ task status to
the GPT text model configured by `OPENAI_TEXT_MODEL`.

Recommended cheap test model:

```env
OPENAI_TEXT_MODEL=gpt-5.4-nano
```

Run:

```powershell
cd C:\RAFFEQ
edge\robot\.venv\Scripts\python.exe scripts\ai_terminal.py
```

Inside the terminal:

```text
sync
tasks
did I eat already?
did I finish lunch or not?
هل أخذت الدواء؟
quit
```

Use this terminal result to judge whether GPT understands the scenario before adding
voice back on top.

## Clean OpenAI voice terminal test

Use this after the text test works. This path records from the laptop microphone,
transcribes with OpenAI, sends the transcript plus synced RAFEEQ task status to the
same GPT text model, then speaks the answer with OpenAI TTS.

It does not use Vosk, Piper, Windows speech, Realtime audio, or the old rule-based
command matcher.

RAFEEQ's default speaking style is Saudi Najdi/Riyadh Arabic: calm, respectful,
friendly like family, and neutral for any patient gender. The assistant should keep
answers short and natural, using phrases like "أبشر", "تم", and "وش تقصد؟" without
overdoing slang.

Required local settings:

```env
OPENAI_TEXT_MODEL=gpt-5.4-nano
OPENAI_TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe
OPENAI_TTS_MODEL=gpt-4o-mini-tts
OPENAI_TTS_VOICE=alloy
VOICE_LISTEN_SECONDS=15
```

Run:

```powershell
cd C:\RAFFEQ
edge\robot\.venv\Scripts\python.exe scripts\ai_voice_terminal.py
```

Inside the terminal:

```text
sync
tasks
record 10
```

You can also press Enter without typing a command to record using
`VOICE_LISTEN_SECONDS`. By default, Rafeeq only speaks the answer and does not print
the AI response text. Use `debug on` only when you need to inspect the transcript or
answer text.

### Voice-created routines

RAFEEQ can create non-medication routine items smoothly when the title and time are
clear. Example:

```text
record 10
```

Say:

```text
add a meeting at 9
```

If you say a clear time such as `9 AM`, `9 PM`, or `21:00`, RAFEEQ saves it
immediately. If you say an ambiguous time such as `9`, RAFEEQ only asks whether you
mean morning or evening, then saves it.

For quick testing without microphone input, use:

```text
text add a meeting at 9
text morning
tasks
```

Medication schedules are stricter: the device voice endpoint rejects medication
creation. Add medication from the caregiver app, or configure a caregiver-authorized
voice token and require full medicine name, dosage, time, and explicit confirmation.

### Voice task completion

RAFEEQ can also update task status in the app. After syncing tasks, say a completion
phrase with the task name:

```text
sync
text I finished lunch
text I took the medicine
text خلصت الغداء
text أخذت الدواء
tasks
```

RAFEEQ publishes a `reminder_completed` device event, the backend marks the matching
routine occurrence as completed with `patient_voice`, and the robot syncs the updated
status locally. If the phrase does not clearly match a task and there is more than
one incomplete task, RAFEEQ asks which task you mean.

## Camera fall voice verification

The laptop camera demo can use the speaker and microphone during a possible fall:

```powershell
cd C:\RAFFEQ
edge\robot\.venv\Scripts\rafeeq-fall-demo.exe --camera-index 0 --detector heuristic --heuristic-confirmation-frames 1 --verification-timeout 10 --speaker openai --voice-verification
```

Flow:

```text
camera sees possible fall
→ Rafeeq asks: "طمني، أنت بخير؟"
→ microphone listens once for 10 seconds
→ "أنا بخير" / "تمام" records a false alarm
→ "ساعدني" / "أحتاج مساعدة" confirms emergency
→ no clear response after 10 seconds confirms emergency by timeout
→ backend sends the caregiver/family emergency alert
```

The normal flow is hands-free: no key press is required after a fall is detected.
The demo only records audio during the verification window. It does not continuously
upload microphone audio. The 10-second timer starts after Rafeeq finishes speaking;
answer after the prompt with "أنا بخير", "تمام", or "ساعدني". Use `F` only as an
optional manual test of the emergency pipeline without performing a real fall. If
OpenAI voice is unavailable, use the keyboard fallback: `S` for safe, `H` for help,
`T` for timeout.

## App task status flow

The app/backend is the source of truth for caregiver-created tasks. Rafeeq answers
task-status questions from the robot's last synchronized local snapshot:

```text
Caregiver creates or completes a task in the app
→ backend stores the routine occurrence
→ robot runs sync
→ voice asks local task status
→ Rafeeq speaks whether the task is completed or not
```

Robot test commands:

```text
sync
voice did I finish lunch or not
voice check memory exercise task status
voice tell me if I took my medicine or not
```

If the robot says no matching task exists, create the task in the app/backend and run
`sync` again. The voice assistant must not guess task completion without a synced
record.

The robot records `voice_command_recognized` with intent and confidence only. It does
not store raw audio or full transcripts.

## Safety rules

- Do not use AI to decide medication dosage, diagnosis, or emergency severity.
- Do not upload continuous microphone audio.
- Do not store raw audio by default.
- Keep SOS and fall verification local and rule-based.
- Use OpenAI voice as a conversational layer that calls explicit RAFEEQ actions:
  `confirm_reminder`, `snooze_reminder`, `decline_reminder`, `request_help`,
  `start_memory_activity`, and `complete_activity`.

## Next implementation step

GPT Realtime is the only interactive assistant reasoning model. The deterministic
local router remains only as a safety fallback for offline core actions. Next
improvements are full speech-to-speech streaming, richer memory activity tools, and
explicit confirmation before any write action such as marking a task complete.
