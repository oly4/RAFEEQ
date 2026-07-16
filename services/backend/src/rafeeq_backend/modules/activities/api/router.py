import base64
import binascii
import json
import re
import urllib.request
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from rafeeq_backend.config import get_settings
from rafeeq_backend.models import ActivityDefinition, ActivityLog, utc_now
from rafeeq_backend.modules.activities.domain.schemas import (
    ActivityCreate,
    ActivityList,
    ActivityLogResponse,
    ActivityResponse,
    PoemSpeechRequest,
    PoemSpeechResponse,
    PoemVoiceTestRequest,
    PoemVoiceTestResponse,
    SavedPoemCreate,
    SavedPoemResponse,
)
from rafeeq_backend.modules.auth.api.dependencies import CurrentUser, DbSession
from rafeeq_backend.modules.patients.application.policies import (
    require_caregiver_access,
    require_patient_access,
)

router = APIRouter(tags=["activities"])

_MAX_AUDIO_BYTES = 10 * 1024 * 1024


def _saved_poem_response(activity: ActivityDefinition) -> SavedPoemResponse:
    return SavedPoemResponse(
        id=activity.id,
        title=activity.title,
        poem_start=activity.description or "",
        expected_completion=activity.instructions or "",
    )


@router.get("/patients/{patient_id}/activities", response_model=ActivityList)
def list_activities(patient_id: str, user: CurrentUser, db: DbSession) -> ActivityList:
    require_patient_access(db, user, patient_id)
    items = list(
        db.scalars(
            select(ActivityDefinition)
            .where(
                ActivityDefinition.patient_id == patient_id,
                ActivityDefinition.is_active.is_(True),
                ActivityDefinition.type != "poem_completion",
            )
            .order_by(ActivityDefinition.created_at.desc())
        ).all()
    )
    return ActivityList(
        items=[ActivityResponse.model_validate(item) for item in items], total=len(items)
    )


@router.post(
    "/patients/{patient_id}/activities",
    response_model=ActivityResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_activity(
    patient_id: str, request: ActivityCreate, user: CurrentUser, db: DbSession
) -> ActivityResponse:
    require_caregiver_access(db, user, patient_id)
    activity = ActivityDefinition(patient_id=patient_id, created_by=user.id, **request.model_dump())
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return ActivityResponse.model_validate(activity)


@router.post("/activities/{activity_id}/start", response_model=ActivityLogResponse)
def start_activity(activity_id: str, user: CurrentUser, db: DbSession) -> ActivityLogResponse:
    activity = db.get(ActivityDefinition, activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    require_caregiver_access(db, user, activity.patient_id)
    log = ActivityLog(activity_id=activity.id, patient_id=activity.patient_id)
    db.add(log)
    db.commit()
    db.refresh(log)
    return ActivityLogResponse.model_validate(log)


@router.post("/activity-logs/{log_id}/complete", response_model=ActivityLogResponse)
def complete_activity(log_id: str, user: CurrentUser, db: DbSession) -> ActivityLogResponse:
    log = db.get(ActivityLog, log_id)
    if log is None:
        raise HTTPException(status_code=404, detail="Activity log not found")
    require_caregiver_access(db, user, log.patient_id)
    if log.status != "completed":
        log.status = "completed"
        log.completed_at = utc_now()
        log.completion_source = "caregiver"
        db.commit()
        db.refresh(log)
    return ActivityLogResponse.model_validate(log)


@router.get(
    "/patients/{patient_id}/activities/poems",
    response_model=list[SavedPoemResponse],
)
def list_saved_poems(patient_id: str, user: CurrentUser, db: DbSession) -> list[SavedPoemResponse]:
    require_patient_access(db, user, patient_id)
    poems = list(
        db.scalars(
            select(ActivityDefinition)
            .where(
                ActivityDefinition.patient_id == patient_id,
                ActivityDefinition.type == "poem_completion",
                ActivityDefinition.is_active.is_(True),
            )
            .order_by(ActivityDefinition.created_at.desc())
        ).all()
    )
    return [_saved_poem_response(item) for item in poems]


@router.post(
    "/patients/{patient_id}/activities/poems",
    response_model=SavedPoemResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_saved_poem(
    patient_id: str, request: SavedPoemCreate, user: CurrentUser, db: DbSession
) -> SavedPoemResponse:
    require_caregiver_access(db, user, patient_id)
    poem = ActivityDefinition(
        patient_id=patient_id,
        type="poem_completion",
        title=request.title.strip(),
        description=request.poem_start.strip(),
        instructions=request.expected_completion.strip(),
        duration_minutes=10,
        created_by=user.id,
    )
    db.add(poem)
    db.commit()
    db.refresh(poem)
    return _saved_poem_response(poem)


@router.delete("/activities/poems/{poem_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_poem(poem_id: str, user: CurrentUser, db: DbSession) -> None:
    poem = db.get(ActivityDefinition, poem_id)
    if poem is None or poem.type != "poem_completion" or not poem.is_active:
        raise HTTPException(status_code=404, detail="Poem not found")
    require_caregiver_access(db, user, poem.patient_id)
    poem.is_active = False
    db.commit()


@router.post(
    "/patients/{patient_id}/activities/poem-speech",
    response_model=PoemSpeechResponse,
)
def create_poem_speech(
    patient_id: str,
    request: PoemSpeechRequest,
    user: CurrentUser,
    db: DbSession,
) -> PoemSpeechResponse:
    require_patient_access(db, user, patient_id)
    prompt_text = (
        "حاضر، بنقرأ بداية القصيدة سوا. اسمع بهدوء، وبعدها كمل اللي تتذكره. "
        f"{request.poem_start.strip()} ... كمل لو تذكرت."
    )
    settings = get_settings()
    api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else ""
    if not api_key:
        return PoemSpeechResponse(prompt_text=prompt_text, used_openai=False)
    audio_data_url = _openai_speech_data_url(
        api_key=api_key,
        model=settings.openai_tts_model,
        voice=settings.openai_tts_voice,
        text=prompt_text,
    )
    return PoemSpeechResponse(
        prompt_text=prompt_text,
        audio_data_url=audio_data_url,
        used_openai=True,
    )


@router.post(
    "/patients/{patient_id}/activities/poem-voice-test",
    response_model=PoemVoiceTestResponse,
)
def evaluate_poem_voice_answer(
    patient_id: str,
    request: PoemVoiceTestRequest,
    user: CurrentUser,
    db: DbSession,
) -> PoemVoiceTestResponse:
    require_patient_access(db, user, patient_id)
    settings = get_settings()
    api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else ""
    if not api_key:
        fallback = _local_poem_answer("", request.expected_completion)
        return PoemVoiceTestResponse(**fallback, transcript="", used_openai=False)

    mime_type, audio_bytes = _decode_data_url(request.audio_data_url)
    if len(audio_bytes) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Voice answer must be 10 MB or smaller")
    transcript = _openai_transcribe_audio(
        api_key=api_key,
        model=settings.openai_transcription_model,
        mime_type=mime_type,
        audio_bytes=audio_bytes,
    )
    fallback = _local_poem_answer(transcript, request.expected_completion)
    ai_answer = _openai_poem_answer(
        api_key=api_key,
        model=settings.openai_text_model,
        poem_start=request.poem_start,
        expected_completion=request.expected_completion,
        transcript=transcript,
        fallback=fallback,
    )
    audio_data_url = _openai_speech_data_url(
        api_key=api_key,
        model=settings.openai_tts_model,
        voice=settings.openai_tts_voice,
        text=ai_answer["assistant_text"],
    )
    return PoemVoiceTestResponse(
        transcript=transcript,
        matched=bool(ai_answer["matched"]),
        assistant_text=str(ai_answer["assistant_text"]),
        hint_text=ai_answer.get("hint_text"),
        audio_data_url=audio_data_url,
        used_openai=True,
    )


def _openai_poem_answer(
    *,
    api_key: str,
    model: str,
    poem_start: str,
    expected_completion: str,
    transcript: str,
    fallback: dict[str, object],
) -> dict[str, object]:
    payload = {
        "model": model,
        "instructions": (
            "You are RAFEEQ, a calm Saudi elder-care memory "
            "assistant. The patient is completing a familiar poem as a memory "
            "exercise. Use clear neutral Saudi Arabic. Your tone is respectful, "
            "calm, patient, and easy to understand for older adults. Do not sound robotic. "
            "Do not use childish or overly intimate words such as حبيبي, حبيبتي, "
            "يا قلبي, يا بعدي, يا الغالي, يا عم, يا خالة. Do not provide medical advice. "
            "Compare the patient's transcript with the expected completion. "
            "Accept close Arabic variants, small speech-to-text mistakes, and "
            "partial but meaningful completion. If the answer is not correct, "
            "do not say 'wrong' and do not reveal the full completion immediately. "
            "Act like a gentle teacher: encourage the patient, give one small hint "
            "using the first few words or the meaning, then invite another try. "
            "Return only compact JSON with keys: "
            "matched:boolean, assistant_text:string, hint_text:string|null."
        ),
        "input": (
            f"Poem start:\n{poem_start}\n\n"
            f"Expected completion:\n{expected_completion}\n\n"
            f"Patient transcript:\n{transcript}"
        ),
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
    parsed = _parse_json_object(_response_text(data)) or fallback
    matched = bool(fallback.get("matched")) or bool(parsed.get("matched"))
    assistant_text = str(parsed.get("assistant_text") or fallback["assistant_text"]).strip()
    if matched and not bool(parsed.get("matched")):
        assistant_text = "صح عليك، ممتاز. كملتها بشكل جميل."
    hint = parsed.get("hint_text")
    hint_text = str(hint).strip() if hint is not None and str(hint).strip() else None
    if not matched:
        safe_hint = hint_text or str(fallback.get("hint_text") or "").strip()
        if not safe_hint:
            safe_hint = _poem_hint(expected_completion)
        assistant_text = f"قريب. تلميح بسيط: {safe_hint}. خذ راحتك، ونحاول مرة ثانية."
        hint_text = safe_hint
    return {
        "matched": matched,
        "assistant_text": _sanitize_voice_assistant_text(assistant_text)[:700],
        "hint_text": None if matched else hint_text,
    }


def _local_poem_answer(transcript: str, expected_completion: str) -> dict[str, object]:
    normalized_transcript = _normalize_arabic(transcript)
    normalized_expected = _normalize_arabic(expected_completion)
    matched = bool(normalized_transcript) and (
        normalized_transcript in normalized_expected or normalized_expected in normalized_transcript
    )
    hint = _poem_hint(expected_completion)
    return {
        "matched": matched,
        "assistant_text": _sanitize_voice_assistant_text(
            "صح عليك، ممتاز. كملتها بشكل جميل."
            if matched
            else f"قريب. تلميح بسيط: {hint}. خذ راحتك، وحاول مرة ثانية."
        ),
        "hint_text": None if matched else hint,
    }


def _sanitize_voice_assistant_text(text: str) -> str:
    banned = (
        "حبيبي",
        "حبيبتي",
        "يا قلبي",
        "يا بعدي",
        "يا الغالي",
        "يا عم",
        "يا خالة",
        "طال عمرك",
        "وشلونك",
        "علومك",
    )
    cleaned = text
    for phrase in banned:
        cleaned = cleaned.replace(phrase, "")
    return " ".join(cleaned.split()).strip() or "حاضر."


def _poem_hint(expected_completion: str) -> str:
    words = expected_completion.strip().split()
    if not words:
        return "تذكر أول كلمة"
    return " ".join(words[: min(3, len(words))])


def _openai_transcribe_audio(
    *, api_key: str, model: str, mime_type: str, audio_bytes: bytes
) -> str:
    extension = {
        "audio/webm": "webm",
        "audio/wav": "wav",
        "audio/mpeg": "mp3",
        "audio/mp4": "m4a",
        "audio/ogg": "ogg",
    }.get(mime_type, "webm")
    boundary = f"----rafeeq{uuid4().hex}"
    body = _multipart_form_data(
        boundary=boundary,
        fields={"model": model, "language": "ar"},
        files={
            "file": (
                f"answer.{extension}",
                mime_type or "audio/webm",
                audio_bytes,
            )
        },
    )
    request = urllib.request.Request(
        "https://api.openai.com/v1/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
    text = data.get("text")
    return text.strip() if isinstance(text, str) else ""


def _openai_speech_data_url(*, api_key: str, model: str, voice: str, text: str) -> str:
    payload = {
        "model": model,
        "voice": voice,
        "input": text,
        "response_format": "wav",
        "instructions": (
            "Speak Arabic clearly in calm neutral Saudi Arabic. "
            "Use a respectful, patient tone for an older adult. Keep sentences short. "
            "Do not sound childish or robotic. Do not use overly intimate phrases "
            "such as حبيبي, يا بعدي, or يا الغالي. Read poem text accurately; "
            "do not change poem words."
        ),
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        audio = response.read()
    encoded = base64.b64encode(audio).decode("ascii")
    return f"data:audio/wav;base64,{encoded}"


def _decode_data_url(data_url: str) -> tuple[str, bytes]:
    if not data_url.startswith("data:") or ";base64," not in data_url:
        raise HTTPException(status_code=422, detail="Payload must be a base64 data URL")
    header, encoded = data_url.split(";base64,", 1)
    mime_type = header.removeprefix("data:").split(";", 1)[0].strip().lower()
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Base64 data is invalid") from exc
    return mime_type, raw


def _multipart_form_data(
    *,
    boundary: str,
    fields: dict[str, str],
    files: dict[str, tuple[str, str, bytes]],
) -> bytes:
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    for name, (filename, content_type, content) in files.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                ).encode(),
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                content,
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks)


def _response_text(data: dict[str, object]) -> str:
    direct = data.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    parts: list[str] = []
    output = data.get("output")
    if not isinstance(output, list):
        return ""
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for piece in content:
            if isinstance(piece, dict) and isinstance(piece.get("text"), str):
                parts.append(piece["text"])
    return "".join(parts).strip()


def _parse_json_object(text: str) -> dict[str, object] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match is None:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _normalize_arabic(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[أإآ]", "ا", text)
    text = text.replace("ى", "ي").replace("ة", "ه")
    text = re.sub(r"[\u064B-\u065F]", "", text)
    return re.sub(r"\s+", " ", text)
