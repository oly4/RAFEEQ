import base64
import binascii
import json
from pathlib import Path
import re
import urllib.request
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from rafeeq_backend.config import get_settings
from rafeeq_backend.models import MemoryCategory, MemoryItem, utc_now
from rafeeq_backend.modules.auth.api.dependencies import CurrentUser, DbSession
from rafeeq_backend.modules.memories.domain.schemas import (
    MemoryAiSpeechRequest,
    MemoryAiSpeechResponse,
    MemoryAiTestRequest,
    MemoryAiTestResponse,
    MemoryAiVoiceTestRequest,
    MemoryAiVoiceTestResponse,
    MemoryCategoryCreate,
    MemoryCategoryResponse,
    MemoryItemCreate,
    MemoryItemResponse,
    MemoryItemUpdate,
    MemoryList,
)
from rafeeq_backend.modules.patients.application.policies import (
    require_caregiver_access,
    require_patient_access,
)

router = APIRouter(tags=["memories"])

_UPLOAD_ROOT = Path(__file__).resolve().parents[7] / "data" / "uploads" / "memories"
_ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_MAX_AUDIO_BYTES = 10 * 1024 * 1024


def _save_uploaded_memory_image(data_url: str) -> str:
    mime_type, image_bytes = _decode_data_url(data_url)
    extension = _ALLOWED_IMAGE_TYPES.get(mime_type)
    if extension is None:
        raise HTTPException(status_code=422, detail="Only JPEG, PNG, and WebP images are supported")

    if len(image_bytes) > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Memory image must be 5 MB or smaller")

    _UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{extension}"
    (_UPLOAD_ROOT / filename).write_bytes(image_bytes)
    return f"/media/memories/{filename}"


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


@router.get("/patients/{patient_id}/memory-categories", response_model=list[MemoryCategoryResponse])
def list_categories(
    patient_id: str, user: CurrentUser, db: DbSession
) -> list[MemoryCategoryResponse]:
    require_patient_access(db, user, patient_id)
    items = db.scalars(
        select(MemoryCategory)
        .where(MemoryCategory.patient_id == patient_id)
        .order_by(MemoryCategory.sort_order)
    ).all()
    return [MemoryCategoryResponse.model_validate(item) for item in items]


@router.post(
    "/patients/{patient_id}/memory-categories",
    response_model=MemoryCategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_category(
    patient_id: str, request: MemoryCategoryCreate, user: CurrentUser, db: DbSession
) -> MemoryCategoryResponse:
    require_caregiver_access(db, user, patient_id)
    category = MemoryCategory(patient_id=patient_id, **request.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    return MemoryCategoryResponse.model_validate(category)


@router.get("/patients/{patient_id}/memories", response_model=MemoryList)
def list_memories(patient_id: str, user: CurrentUser, db: DbSession) -> MemoryList:
    require_patient_access(db, user, patient_id)
    items = list(
        db.scalars(
            select(MemoryItem)
            .where(MemoryItem.patient_id == patient_id, MemoryItem.deleted_at.is_(None))
            .order_by(MemoryItem.created_at.desc())
        ).all()
    )
    return MemoryList(
        items=[MemoryItemResponse.model_validate(item) for item in items], total=len(items)
    )


@router.post(
    "/patients/{patient_id}/memories",
    response_model=MemoryItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_memory(
    patient_id: str, request: MemoryItemCreate, user: CurrentUser, db: DbSession
) -> MemoryItemResponse:
    require_caregiver_access(db, user, patient_id)
    category = db.get(MemoryCategory, request.category_id)
    if category is None or category.patient_id != patient_id:
        raise HTTPException(status_code=422, detail="Memory category is invalid")
    values = request.model_dump(exclude={"people_labels", "upload_data_url"})
    if request.upload_data_url:
        values["object_key_or_url"] = _save_uploaded_memory_image(request.upload_data_url)
        values["media_type"] = "photo"
    memory = MemoryItem(
        patient_id=patient_id,
        created_by=user.id,
        people_labels_json=request.people_labels,
        **values,
    )
    db.add(memory)
    db.commit()
    db.refresh(memory)
    return MemoryItemResponse.model_validate(memory)


def _caregiver_memory(db: DbSession, memory_id: str, user: CurrentUser) -> MemoryItem:
    memory = db.get(MemoryItem, memory_id)
    if memory is None or memory.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Memory item not found")
    require_caregiver_access(db, user, memory.patient_id)
    return memory


@router.patch("/memories/{memory_id}", response_model=MemoryItemResponse)
def update_memory(
    memory_id: str, request: MemoryItemUpdate, user: CurrentUser, db: DbSession
) -> MemoryItemResponse:
    memory = _caregiver_memory(db, memory_id, user)
    if request.category_id is not None:
        category = db.get(MemoryCategory, request.category_id)
        if category is None or category.patient_id != memory.patient_id:
            raise HTTPException(status_code=422, detail="Memory category is invalid")
        memory.category_id = request.category_id
    if request.title is not None:
        memory.title = request.title.strip()
    if request.description is not None:
        memory.description = request.description.strip() or None
    if request.people_labels is not None:
        memory.people_labels_json = [
            label.strip() for label in request.people_labels if label.strip()
        ]
    if request.spoken_prompt is not None:
        memory.spoken_prompt = request.spoken_prompt.strip() or None
    if request.visibility is not None:
        memory.visibility = request.visibility
    db.commit()
    db.refresh(memory)
    return MemoryItemResponse.model_validate(memory)


@router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(memory_id: str, user: CurrentUser, db: DbSession) -> None:
    memory = _caregiver_memory(db, memory_id, user)
    memory.deleted_at = utc_now()
    db.commit()


@router.post(
    "/patients/{patient_id}/memories/{memory_id}/ai-test",
    response_model=MemoryAiTestResponse,
)
def evaluate_memory_answer(
    patient_id: str,
    memory_id: str,
    request: MemoryAiTestRequest,
    user: CurrentUser,
    db: DbSession,
) -> MemoryAiTestResponse:
    require_patient_access(db, user, patient_id)
    memory = db.get(MemoryItem, memory_id)
    if memory is None or memory.patient_id != patient_id or memory.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Memory item not found")

    fallback = _local_memory_answer(memory, request.answer_text)
    settings = get_settings()
    api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else ""
    if not api_key:
        return fallback

    try:
        return _openai_memory_answer(
            api_key=api_key,
            model=settings.openai_text_model,
            memory=memory,
            answer_text=request.answer_text,
            fallback=fallback,
        )
    except Exception:
        return fallback


@router.post(
    "/patients/{patient_id}/memories/{memory_id}/ai-speech",
    response_model=MemoryAiSpeechResponse,
)
def create_memory_ai_speech(
    patient_id: str,
    memory_id: str,
    request: MemoryAiSpeechRequest,
    user: CurrentUser,
    db: DbSession,
) -> MemoryAiSpeechResponse:
    require_patient_access(db, user, patient_id)
    memory = db.get(MemoryItem, memory_id)
    if memory is None or memory.patient_id != patient_id or memory.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Memory item not found")
    settings = get_settings()
    api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else ""
    if not api_key:
        return MemoryAiSpeechResponse(assistant_text=request.text, used_openai=False)
    audio_data_url = _openai_speech_data_url(
        api_key=api_key,
        model=settings.openai_tts_model,
        voice=settings.openai_tts_voice,
        text=request.text,
    )
    return MemoryAiSpeechResponse(
        assistant_text=request.text,
        audio_data_url=audio_data_url,
        used_openai=True,
    )


@router.post(
    "/patients/{patient_id}/memories/{memory_id}/ai-voice-test",
    response_model=MemoryAiVoiceTestResponse,
)
def evaluate_memory_voice_answer(
    patient_id: str,
    memory_id: str,
    request: MemoryAiVoiceTestRequest,
    user: CurrentUser,
    db: DbSession,
) -> MemoryAiVoiceTestResponse:
    require_patient_access(db, user, patient_id)
    memory = db.get(MemoryItem, memory_id)
    if memory is None or memory.patient_id != patient_id or memory.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Memory item not found")

    settings = get_settings()
    api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else ""
    if not api_key:
        fallback = _local_memory_answer(memory, "")
        return MemoryAiVoiceTestResponse(**fallback.model_dump(), transcript="")

    mime_type, audio_bytes = _decode_data_url(request.audio_data_url)
    if len(audio_bytes) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Voice answer must be 10 MB or smaller")
    transcript = _openai_transcribe_audio(
        api_key=api_key,
        model=settings.openai_transcription_model,
        mime_type=mime_type,
        audio_bytes=audio_bytes,
    )
    fallback = _local_memory_answer(memory, transcript)
    answer = _openai_memory_answer(
        api_key=api_key,
        model=settings.openai_text_model,
        memory=memory,
        answer_text=transcript,
        fallback=fallback,
    )
    audio_data_url = _openai_speech_data_url(
        api_key=api_key,
        model=settings.openai_tts_model,
        voice=settings.openai_tts_voice,
        text=answer.assistant_text,
    )
    return MemoryAiVoiceTestResponse(
        **answer.model_dump(),
        transcript=transcript,
        audio_data_url=audio_data_url,
    )


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
        "response_format": "mp3",
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
    return f"data:audio/mpeg;base64,{encoded}"


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


def _openai_memory_answer(
    *,
    api_key: str,
    model: str,
    memory: MemoryItem,
    answer_text: str,
    fallback: MemoryAiTestResponse,
) -> MemoryAiTestResponse:
    payload = {
        "model": model,
        "instructions": (
            "You are RAFEEQ, a calm Saudi elder-care memory "
            "assistant. The patient is doing a gentle photo-recognition activity. "
            "Use clear neutral Saudi Arabic. Be short, respectful, patient, and calm. "
            "Do not use childish or overly intimate words such as حبيبي, حبيبتي, "
            "يا قلبي, يا بعدي, يا الغالي, يا عم, يا خالة. "
            "Do not give medical diagnosis or medical advice. "
            "Judge whether the patient's answer identifies the person or memory. "
            "Accept close Arabic variants, nicknames, partial family names, and small "
            "speech-to-text mistakes. If the answer is not correct, never reveal the "
            "final answer immediately. Act like a gentle memory game coach: give one "
            "small hint from the provided hint/description/relationship, then invite "
            "another try. Avoid saying 'wrong'. Return only compact JSON with keys: "
            "matched:boolean, assistant_text:string, hint_text:string|null."
        ),
        "input": (
            "Memory item JSON:\n"
            f"{json.dumps(_memory_context(memory), ensure_ascii=False)}\n\n"
            f"Patient answer transcript: {answer_text}"
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
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    text = _response_text(data)
    parsed = _parse_json_object(text)
    if not parsed:
        return fallback
    assistant_text = str(parsed.get("assistant_text") or fallback.assistant_text).strip()
    hint = parsed.get("hint_text")
    hint_text = str(hint).strip() if hint is not None and str(hint).strip() else None
    matched = fallback.matched or bool(parsed.get("matched", fallback.matched))
    if fallback.matched and not bool(parsed.get("matched", False)):
        assistant_text = "صح، ممتاز. إجابتك صحيحة."
        hint_text = None
    elif not matched:
        safe_hint = hint_text or fallback.hint_text or "خذ وقتك وحاول تتذكر بهدوء."
        assistant_text = f"قريب. تلميح بسيط: {safe_hint}. خذ راحتك، وحاول مرة ثانية."
        hint_text = safe_hint
    return MemoryAiTestResponse(
        matched=matched,
        assistant_text=_sanitize_voice_assistant_text(assistant_text)[:500],
        hint_text=None if matched else hint_text[:500] if hint_text else None,
        used_openai=True,
    )


def _memory_context(memory: MemoryItem) -> dict[str, object]:
    return {
        "title": memory.title,
        "description": memory.description,
        "accepted_people_or_answers": memory.people_labels_json,
        "hint": memory.spoken_prompt,
    }


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


def _local_memory_answer(memory: MemoryItem, answer_text: str) -> MemoryAiTestResponse:
    accepted_answers = [memory.title, *(memory.people_labels_json or [])]
    normalized_answer = _normalize_arabic(answer_text)
    matched = bool(normalized_answer) and any(
        normalized_answer in _normalize_arabic(item) or _normalize_arabic(item) in normalized_answer
        for item in accepted_answers
        if item
    )
    hint = memory.spoken_prompt or memory.description or "حاول تتذكر مين يزورك كثير."
    return MemoryAiTestResponse(
        matched=matched,
        assistant_text=_sanitize_voice_assistant_text(
            "صح، ممتاز. إجابتك صحيحة."
            if matched
            else f"مو مشكلة. تلميح بسيط: {hint}. خذ راحتك وحاول مرة ثانية."
        ),
        hint_text=None if matched else hint,
        used_openai=False,
    )


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


def _normalize_arabic(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[أإآ]", "ا", text)
    text = text.replace("ى", "ي").replace("ة", "ه")
    text = re.sub(r"[\u064B-\u065F]", "", text)
    return re.sub(r"\s+", " ", text)
