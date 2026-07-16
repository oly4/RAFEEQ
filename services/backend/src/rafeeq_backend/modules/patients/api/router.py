import json
import re
import urllib.request
from datetime import datetime, time, timezone
from itertools import count
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from rafeeq_backend.config import get_settings
from rafeeq_backend.models import (
    CaregiverPatient,
    Device,
    EmergencyEvent,
    EmergencyContact,
    MedicationDetail,
    Patient,
    Routine,
    RoutineOccurrence,
    User,
    utc_now,
)
from rafeeq_backend.modules.activities.api.router import (
    _decode_data_url,
    _openai_speech_data_url,
    _openai_transcribe_audio,
    _parse_json_object,
    _response_text,
)
from rafeeq_backend.modules.auth.api.dependencies import CurrentUser, DbSession
from rafeeq_backend.modules.patients.application.policies import (
    require_caregiver_access,
    require_patient_access,
)
from rafeeq_backend.modules.patients.domain.schemas import (
    AlertRecipientResponse,
    CareProfileResponse,
    CareProfileUpdate,
    DashboardSummary,
    EmergencyContactCreate,
    EmergencyContactResponse,
    PatientCreate,
    PatientList,
    PatientResponse,
    PatientUpdate,
    VoiceCommandRequest,
    VoiceCommandResponse,
)

router = APIRouter(tags=["patients"])

_VOICE_COMMAND_SEQUENCE = count(1)
_VOICE_COMMAND_EVENTS: dict[str, list[dict[str, object]]] = {}


@router.get("/patients", response_model=PatientList)
def list_patients(user: CurrentUser, db: DbSession) -> PatientList:
    if user.role == "caregiver":
        statement = (
            select(Patient)
            .join(CaregiverPatient)
            .where(CaregiverPatient.caregiver_user_id == user.id)
        )
    elif user.role == "doctor":
        from rafeeq_backend.models import DoctorPatient

        statement = (
            select(Patient)
            .join(DoctorPatient)
            .where(
                DoctorPatient.doctor_user_id == user.id,
                DoctorPatient.revoked_at.is_(None),
            )
        )
    else:
        statement = select(Patient)
    patients = list(db.scalars(statement.order_by(Patient.created_at.desc())).all())
    return PatientList(
        items=[PatientResponse.model_validate(item) for item in patients], total=len(patients)
    )


@router.post("/patients", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
def create_patient(request: PatientCreate, user: CurrentUser, db: DbSession) -> PatientResponse:
    if user.role != "caregiver":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only caregivers create patients"
        )
    patient = Patient(
        display_name=request.display_name.strip(),
        date_of_birth=request.date_of_birth,
        condition_notes=request.condition_notes,
        preferred_language=request.preferred_language,
        timezone=request.timezone,
        emergency_instructions=request.emergency_instructions,
    )
    db.add(patient)
    db.flush()
    db.add(
        CaregiverPatient(
            caregiver_user_id=user.id,
            patient_id=patient.id,
            relationship_label=request.relationship_label,
            is_primary=True,
            permissions_json={"manage": True},
        )
    )
    db.commit()
    db.refresh(patient)
    return PatientResponse.model_validate(patient)


@router.get("/patients/{patient_id}", response_model=PatientResponse)
def get_patient(patient_id: str, user: CurrentUser, db: DbSession) -> PatientResponse:
    require_patient_access(db, user, patient_id)
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return PatientResponse.model_validate(patient)


@router.patch("/patients/{patient_id}", response_model=PatientResponse)
def update_patient(
    patient_id: str, request: PatientUpdate, user: CurrentUser, db: DbSession
) -> PatientResponse:
    require_caregiver_access(db, user, patient_id)
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(patient, field, value)
    db.commit()
    db.refresh(patient)
    return PatientResponse.model_validate(patient)


@router.get("/patients/{patient_id}/dashboard", response_model=DashboardSummary)
def patient_dashboard(patient_id: str, user: CurrentUser, db: DbSession) -> DashboardSummary:
    require_patient_access(db, user, patient_id)
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    try:
        patient_zone = ZoneInfo(patient.timezone)
    except ZoneInfoNotFoundError:
        patient_zone = timezone.utc
    today = datetime.now(patient_zone).date()
    day_start = datetime.combine(today, time.min, tzinfo=patient_zone).astimezone(timezone.utc)
    day_end = datetime.combine(today, time.max, tzinfo=patient_zone).astimezone(timezone.utc)
    occurrences = list(
        db.scalars(
            select(RoutineOccurrence).where(
                RoutineOccurrence.patient_id == patient_id,
                RoutineOccurrence.scheduled_at_utc >= day_start,
                RoutineOccurrence.scheduled_at_utc <= day_end,
            )
        ).all()
    )
    active_medication_routines = list(
        db.scalars(
            select(Routine).where(
                Routine.patient_id == patient_id,
                Routine.type == "medication",
                Routine.is_active.is_(True),
                Routine.start_date <= today,
                (Routine.end_date.is_(None) | (Routine.end_date >= today)),
            )
        ).all()
    )
    medication_ids = {routine.id for routine in active_medication_routines}
    completed = [item for item in occurrences if item.status == "completed"]
    medication = [item for item in occurrences if item.routine_id in medication_ids]
    medication_completed = [item for item in medication if item.status == "completed"]
    medication_total = len(medication) if medication else len(active_medication_routines)
    medication_completed_total = len(medication_completed)
    medication_pending = max(0, medication_total - medication_completed_total)
    active_emergencies = (
        db.scalar(
            select(func.count())
            .select_from(EmergencyEvent)
            .where(
                EmergencyEvent.patient_id == patient_id,
                EmergencyEvent.status.not_in(("resolved", "false_alarm")),
            )
        )
        or 0
    )
    device = db.scalar(
        select(Device).where(Device.patient_id == patient_id).order_by(Device.created_at.desc())
    )
    completion = round(len(completed) * 100 / len(occurrences)) if occurrences else 0
    return DashboardSummary(
        patient=PatientResponse.model_validate(patient),
        device_status=device.status if device else "unpaired",
        daily_completion_percentage=completion,
        medication_total=medication_total,
        medication_completed=medication_completed_total,
        medication_pending=medication_pending,
        routine_total=len(occurrences),
        routine_completed=len(completed),
        active_emergencies=active_emergencies,
    )


@router.post("/patients/{patient_id}/voice-command", response_model=VoiceCommandResponse)
def handle_voice_command(
    patient_id: str,
    request: VoiceCommandRequest,
    user: CurrentUser,
    db: DbSession,
) -> VoiceCommandResponse:
    require_patient_access(db, user, patient_id)
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    settings = get_settings()
    api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else ""
    if not api_key:
        return VoiceCommandResponse(
            action="unknown",
            assistant_text="ما قدرت أتصل بالذكاء الاصطناعي. تأكد من إعداد OpenAI.",
        )

    mime_type, audio_bytes = _decode_data_url(request.audio_data_url)
    transcript = _openai_transcribe_audio(
        api_key=api_key,
        model=settings.openai_transcription_model,
        mime_type=mime_type,
        audio_bytes=audio_bytes,
    )
    routine_context = _voice_routine_context(db, patient)
    parsed = _openai_parse_voice_command(
        api_key=api_key,
        model=settings.openai_text_model,
        transcript=transcript,
        routine_context=routine_context,
    )
    local_parsed = _local_parse_voice_command(transcript, routine_context)
    if _should_use_local_voice_parse(parsed, local_parsed):
        parsed = local_parsed
    action = str(parsed.get("action") or "unknown")
    allowed_actions = {
        "open_dashboard",
        "open_routine",
        "open_activities",
        "open_album",
        "open_settings",
        "start_poem_test",
        "start_photo_test",
        "add_routine",
        "edit_routine",
        "delete_routine",
        "complete_routine",
        "undo_complete_routine",
        "unknown",
    }
    if action not in allowed_actions:
        action = "unknown"

    assistant_text = str(parsed.get("assistant_text") or "").strip()
    if action == "unknown":
        assistant_text = ""
    routine_created = False
    routine_title = None
    needs_confirmation = bool(parsed.get("needs_confirmation", False))
    if action in {
        "add_routine",
        "edit_routine",
        "delete_routine",
        "complete_routine",
        "undo_complete_routine",
    }:
        if user.role != "caregiver":
            action = "unknown"
            assistant_text = "هذا الأمر يحتاج حساب العائلة عشان أقدر أغيّر الروتين."
            needs_confirmation = True
        elif needs_confirmation:
            assistant_text = assistant_text or "أحتاج تفاصيل أوضح قبل أغيّر الروتين."
        elif action == "add_routine":
            routine_data = parsed.get("routine")
            if isinstance(routine_data, dict):
                created = _create_voice_routine(db, patient, user, routine_data)
                if created is not None:
                    routine_created = True
                    routine_title = created.title
                    assistant_text = assistant_text or f"تم، أضفت {created.title} للروتين."
                else:
                    needs_confirmation = True
                    assistant_text = (
                        "فهمت إنك تبي تضيف روتين، بس ناقصني الاسم أو الوقت. "
                        "قل مثلًا: أضف موعد مشي الساعة خمسة مساء."
                    )
            else:
                needs_confirmation = True
                assistant_text = assistant_text or "قل اسم المهمة والوقت عشان أضيفها."
        elif action == "edit_routine":
            changed = _edit_voice_routine(db, patient, user, parsed)
            if changed is None:
                needs_confirmation = True
                assistant_text = (
                    assistant_text or "ما لقيت المهمة المقصودة. قل اسمها والوقت الجديد بوضوح."
                )
            else:
                routine_title = changed.title
                assistant_text = assistant_text or f"تم، عدّلت {changed.title}."
        elif action == "delete_routine":
            deleted_title = _delete_voice_routine(db, patient, user, parsed)
            if deleted_title is None:
                needs_confirmation = True
                assistant_text = assistant_text or "ما لقيت المهمة اللي تبي أحذفها. قل اسمها بوضوح."
            else:
                routine_title = deleted_title
                assistant_text = assistant_text or f"تم، حذفت {deleted_title} من الروتين."
        elif action == "complete_routine":
            completed_title = _set_voice_occurrence_status(
                db, patient, user, parsed, completed=True
            )
            if completed_title is None:
                needs_confirmation = True
                assistant_text = assistant_text or "ما لقيت مهمة مناسبة أعلّمها كتم. قل اسم المهمة."
            else:
                routine_title = completed_title
                assistant_text = assistant_text or f"تم، علّمت {completed_title} كمنجزة."
        elif action == "undo_complete_routine":
            undone_title = _set_voice_occurrence_status(db, patient, user, parsed, completed=False)
            if undone_title is None:
                needs_confirmation = True
                assistant_text = assistant_text or "ما لقيت مهمة مكتملة أشيل منها علامة تم."
            else:
                routine_title = undone_title
                assistant_text = assistant_text or f"تم، شلت علامة تم من {undone_title}."

    if not assistant_text:
        assistant_text = _voice_action_default_text(action)
    assistant_text = _sanitize_voice_assistant_text(assistant_text)
    audio_data_url = _openai_speech_data_url(
        api_key=api_key,
        model=settings.openai_tts_model,
        voice=settings.openai_tts_voice,
        text=assistant_text,
    )
    response_payload = VoiceCommandResponse(
        transcript=transcript,
        action=action,  # type: ignore[arg-type]
        assistant_text=assistant_text,
        audio_data_url=audio_data_url,
        routine_created=routine_created,
        routine_title=routine_title,
        needs_confirmation=needs_confirmation,
        used_openai=True,
    )
    if request.emit_event:
        _store_voice_command_event(patient_id, response_payload)
    return response_payload


@router.get("/patients/{patient_id}/voice-command-events")
def list_voice_command_events(
    patient_id: str,
    user: CurrentUser,
    db: DbSession,
    since: int = 0,
) -> dict[str, object]:
    require_patient_access(db, user, patient_id)
    items = [
        item
        for item in _VOICE_COMMAND_EVENTS.get(patient_id, [])
        if int(item.get("sequence", 0)) > since
    ]
    latest_sequence = since
    if items:
        latest_sequence = max(int(item.get("sequence", since)) for item in items)
    return {"items": items, "latest_sequence": latest_sequence}


def _store_voice_command_event(patient_id: str, response: VoiceCommandResponse) -> None:
    event = response.model_dump()
    event["assistant_text"] = ""
    event["audio_data_url"] = None
    event["sequence"] = next(_VOICE_COMMAND_SEQUENCE)
    events = _VOICE_COMMAND_EVENTS.setdefault(patient_id, [])
    events.append(event)
    del events[:-20]


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


def _openai_parse_voice_command(
    *,
    api_key: str,
    model: str,
    transcript: str,
    routine_context: list[dict[str, object]],
) -> dict[str, object]:
    payload = {
        "model": model,
        "instructions": (
            "You are the command planner for RAFEEQ, an Arabic elder-care app. "
            "Understand clear Saudi Arabic voice commands, including common local phrasing, "
            "but keep responses in natural neutral Saudi Arabic. Return only compact JSON. "
            "Allowed action values: open_dashboard, open_routine, open_activities, "
            "open_album, open_settings, start_poem_test, start_photo_test, "
            "add_routine, edit_routine, delete_routine, complete_routine, "
            "undo_complete_routine, unknown. "
            "For navigation/test commands, no confirmation is needed. "
            "If the user asks to play, start, choose, or test a poem/poetry/قصيدة, "
            "use start_poem_test. "
            "Assistant text must be short spoken Arabic: calm, respectful, patient, "
            "and suitable for older adults. Use polite phrases like أبشر, حاضر, "
            "الله يعافيك, خذ راحتك. Do not use childish or overly intimate words "
            "such as حبيبي, حبيبتي, يا قلبي, يا بعدي, يا الغالي, يا عم, يا خالة. "
            "Do not use Egyptian, Levantine, or Moroccan dialect. "
            "Do not give medical advice, diagnosis, or medication dosage changes. "
            "Do not claim an action succeeded unless the app/backend action actually succeeds. "
            "For unknown commands, assistant_text must be exactly short and simple; "
            "do not ask detailed clarification, do not list examples, and do not "
            "suggest poem/photo tests unless the user clearly asked for them. "
            "For routine completion, deletion, and editing, use the provided routine "
            "context and return target_routine_id or target_occurrence_id when possible. "
            "If the user says they did/finished/took a task, use complete_routine. "
            "If the user says undo/not done/remove done mark, use undo_complete_routine. "
            "If the user says delete/remove a task, use delete_routine only when the "
            "target is clear from the current routines; otherwise needs_confirmation true. "
            "If the user says change/move/rename a task, use edit_routine and include "
            "routine patch fields: title, time_24h, description, medication. "
            "For add_routine, only if the user clearly says task/title and time, set "
            "needs_confirmation false and include routine object: "
            "{type:'appointment'|'meal'|'water'|'spiritual'|'memory_exercise'|"
            "'conversation'|'custom'|'medication', title:string, "
            "time_24h:'HH:MM', description:string|null, "
            "medication:{medication_name:string,dosage_text:string,instructions:string|null}|null}. "
            "Medication reminders need at least medicine name and time; if dose is not "
            "spoken use dosage_text:'حسب الوصفة'. "
            "Return keys: action, assistant_text, needs_confirmation, routine, "
            "target_routine_id, target_occurrence_id, target_title, patch."
        ),
        "input": (
            f"Current routines JSON:\n{json.dumps(routine_context, ensure_ascii=False)}\n\n"
            f"Voice transcript:\n{transcript}"
        ),
    }
    http_request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(http_request, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
    return _parse_json_object(_response_text(data)) or {
        "action": "unknown",
        "assistant_text": "عذرًا، ما سمعت الكلام كاملًا. هل تسمح تعيده بهدوء؟",
        "needs_confirmation": False,
    }


def _should_use_local_voice_parse(
    parsed: dict[str, object], local_parsed: dict[str, object]
) -> bool:
    local_action = str(local_parsed.get("action") or "unknown")
    if local_action == "unknown":
        return False
    parsed_action = str(parsed.get("action") or "unknown")
    if parsed_action == "unknown" or bool(parsed.get("needs_confirmation", False)):
        return True
    return local_action in {
        "add_routine",
        "edit_routine",
        "delete_routine",
        "complete_routine",
        "undo_complete_routine",
    } and parsed_action not in {
        "open_dashboard",
        "open_routine",
        "open_activities",
        "open_album",
        "open_settings",
        "start_poem_test",
        "start_photo_test",
    }


def _local_parse_voice_command(
    transcript: str, routine_context: list[dict[str, object]]
) -> dict[str, object]:
    text = _normalize_spoken_digits(transcript)
    normalized = _normalize_voice_text(text)
    if not normalized:
        return {"action": "unknown", "needs_confirmation": False}

    target = _local_routine_target(text, routine_context)
    has_done_word = _contains_any(
        normalized,
        (
            "تم",
            "خلصت",
            "انجزت",
            "سويت",
            "اخذت",
            "اكلت",
            "انتهيت",
            "done",
            "finished",
            "took",
        ),
    )
    has_undo_word = _contains_any(
        normalized,
        (
            "شيلتم",
            "ازلتم",
            "الغتم",
            "الغاءتم",
            "موتم",
            "ماتم",
            "ماخلصت",
            "مااخذت",
            "رجعها",
            "undone",
            "undo",
            "notdone",
        ),
    )
    if has_undo_word:
        return {
            "action": "undo_complete_routine",
            "assistant_text": "حاضر، شلت علامة تم.",
            "needs_confirmation": False,
            **target,
        }
    if has_done_word and target:
        return {
            "action": "complete_routine",
            "assistant_text": "تم، علمتها كمنجزة.",
            "needs_confirmation": False,
            **target,
        }

    has_delete_word = _contains_any(
        normalized,
        ("احذف", "حذف", "امسح", "شيل", "ازل", "remove", "delete"),
    )
    if has_delete_word and target:
        return {
            "action": "delete_routine",
            "assistant_text": "تم، حذفتها من الروتين.",
            "needs_confirmation": False,
            **target,
        }

    has_edit_word = _contains_any(
        normalized,
        ("عدل", "غير", "انقل", "بدل", "خل", "change", "edit", "move"),
    )
    parsed_time = _extract_voice_time(text)
    if has_edit_word and target and parsed_time:
        return {
            "action": "edit_routine",
            "assistant_text": "تم، عدلت وقت المهمة.",
            "needs_confirmation": False,
            **target,
            "patch": {"time_24h": parsed_time},
        }

    has_add_word = _contains_any(
        normalized,
        (
            "اضف",
            "حط",
            "سجل",
            "سو",
            "سوي",
            "ذكرني",
            "ضيف",
            "add",
            "create",
            "remind",
        ),
    )
    if has_add_word and parsed_time:
        routine = _local_routine_payload(text, parsed_time)
        if routine is not None:
            return {
                "action": "add_routine",
                "assistant_text": f"تم، أضفت {routine['title']} للروتين.",
                "needs_confirmation": False,
                "routine": routine,
            }

    if _contains_any(normalized, ("روتين", "المهام", "المهاماليوم", "routine")):
        return {
            "action": "open_routine",
            "assistant_text": "تم، فتحت لك الروتين.",
            "needs_confirmation": False,
        }

    return {"action": "unknown", "needs_confirmation": False}


def _contains_any(normalized_text: str, values: tuple[str, ...]) -> bool:
    return any(_normalize_voice_text(value) in normalized_text for value in values)


def _normalize_spoken_digits(value: str) -> str:
    arabic_digits = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
    return value.translate(arabic_digits)


def _local_routine_target(
    transcript: str, routine_context: list[dict[str, object]]
) -> dict[str, object]:
    normalized_transcript = _normalize_voice_text(_normalize_spoken_digits(transcript))
    best: dict[str, object] = {}
    best_score = 0
    for routine in routine_context:
        title = str(routine.get("title") or "")
        normalized_title = _normalize_voice_text(title)
        if not normalized_title:
            continue
        score = 0
        if normalized_title in normalized_transcript:
            score = len(normalized_title) + 10
        else:
            title_words = [
                _normalize_voice_text(word)
                for word in re.split(r"\s+", title)
                if len(_normalize_voice_text(word)) >= 3
            ]
            score = sum(len(word) for word in title_words if word and word in normalized_transcript)
        if score > best_score:
            best_score = score
            best = {
                "target_title": title,
                "target_routine_id": routine.get("routine_id"),
                "target_occurrence_id": routine.get("occurrence_id"),
            }
    return best if best_score >= 3 else {}


def _extract_voice_time(transcript: str) -> str | None:
    text = _normalize_spoken_digits(transcript).lower()
    match = re.search(r"\b([01]?\d|2[0-3])[:٫.]([0-5]\d)\b", text)
    if match:
        return f"{int(match.group(1)):02d}:{int(match.group(2)):02d}"

    hour_value: int | None = None
    minute_value = 0
    hour_match = re.search(
        r"(?:الساعة|ساعه|ساعة|at|@)\s*([0-9]{1,2}|[اأإآ]?[a-z\u0600-\u06ff]+)",
        text,
        re.IGNORECASE,
    )
    if hour_match:
        hour_value = _spoken_hour_to_int(hour_match.group(1))
    else:
        loose_match = re.search(r"\b([0-9]{1,2})\s*(?:ص|م|am|pm)\b", text)
        if loose_match:
            hour_value = int(loose_match.group(1))

    if hour_value is None:
        return None

    minute_match = re.search(r"(?:و|:)\s*([0-5]?\d)\s*(?:دقيقة|دقايق)?", text)
    if minute_match and ":" not in minute_match.group(0):
        minute_value = int(minute_match.group(1))

    evening = _contains_any(
        _normalize_voice_text(text),
        ("مساء", "المساء", "الليل", "العصر", "pm", "بعدالظهر"),
    )
    morning = _contains_any(_normalize_voice_text(text), ("صباح", "الصباح", "am", "الفجر"))
    if evening and 1 <= hour_value <= 11:
        hour_value += 12
    if morning and hour_value == 12:
        hour_value = 0
    if hour_value > 23 or minute_value > 59:
        return None
    return f"{hour_value:02d}:{minute_value:02d}"


def _spoken_hour_to_int(value: str) -> int | None:
    cleaned = _normalize_voice_text(_normalize_spoken_digits(value))
    if cleaned.isdigit():
        return int(cleaned)
    hour_words = {
        "واحد": 1,
        "الوحده": 1,
        "الاوله": 1,
        "اثنين": 2,
        "الثنتين": 2,
        "الثانيه": 2,
        "ثلاث": 3,
        "الثالثه": 3,
        "اربعه": 4,
        "الرابعه": 4,
        "خمس": 5,
        "الخامسه": 5,
        "سته": 6,
        "السادسه": 6,
        "سبعه": 7,
        "السابعه": 7,
        "ثمانيه": 8,
        "الثامنه": 8,
        "تسعه": 9,
        "التاسعه": 9,
        "عشره": 10,
        "العاشره": 10,
        "احدىعشر": 11,
        "احدعشر": 11,
        "الحاديهعشر": 11,
        "اثناعشر": 12,
        "الثانيهعشر": 12,
    }
    return hour_words.get(cleaned)


def _local_routine_payload(transcript: str, time_24h: str) -> dict[str, object] | None:
    normalized = _normalize_voice_text(transcript)
    routine_type = "custom"
    if _contains_any(normalized, ("دواء", "علاج", "حبوب", "جرعه", "medicine", "medication")):
        routine_type = "medication"
    elif _contains_any(normalized, ("موعد", "اجتماع", "لقاء", "appointment", "meeting")):
        routine_type = "appointment"
    elif _contains_any(normalized, ("غداء", "فطور", "عشاء", "اكل", "lunch", "dinner", "breakfast")):
        routine_type = "meal"
    elif _contains_any(normalized, ("مويه", "ماء", "اشرب", "water")):
        routine_type = "water"
    elif _contains_any(normalized, ("قران", "قرآن", "صلاه", "دعاء")):
        routine_type = "spiritual"

    title = _extract_routine_title(transcript)
    if not title:
        title = {
            "medication": "تذكير دواء",
            "appointment": "موعد",
            "meal": "وجبة",
            "water": "شرب الماء",
            "spiritual": "نشاط روحاني",
        }.get(routine_type, "مهمة جديدة")
    routine: dict[str, object] = {
        "type": routine_type,
        "title": title,
        "time_24h": time_24h,
        "description": None,
        "medication": None,
    }
    if routine_type == "medication":
        routine["medication"] = {
            "medication_name": title,
            "dosage_text": "حسب الوصفة",
            "instructions": None,
        }
    return routine


def _extract_routine_title(transcript: str) -> str:
    text = _normalize_spoken_digits(transcript)
    text = re.sub(r"\b(add|create|remind me|at|pm|am)\b", " ", text, flags=re.I)
    text = re.sub(r"(?:الساعة|ساعه|ساعة)\s*[\w\u0600-\u06ff:٫.]+", " ", text)
    text = re.sub(r"\b[0-9]{1,2}[:٫.]?[0-9]{0,2}\s*(?:ص|م|am|pm)?\b", " ", text)
    for word in (
        "أضف",
        "اضف",
        "ضيف",
        "حط",
        "سجل",
        "سو",
        "سوي",
        "ذكرني",
        "روتين",
        "مهمة",
        "مهمه",
        "تذكير",
        "مساء",
        "المساء",
        "صباح",
        "الصباح",
        "الليل",
        "العصر",
    ):
        text = text.replace(word, " ")
    title = " ".join(text.split()).strip(" -،,")
    return title[:80]


def _patient_zone(patient: Patient) -> ZoneInfo | timezone:
    try:
        return ZoneInfo(patient.timezone)
    except ZoneInfoNotFoundError:
        return timezone.utc


def _voice_routine_context(db: DbSession, patient: Patient) -> list[dict[str, object]]:
    local_zone = _patient_zone(patient)
    today = datetime.now(local_zone).date()
    day_start = datetime.combine(today, time.min, tzinfo=local_zone).astimezone(timezone.utc)
    day_end = datetime.combine(today, time.max, tzinfo=local_zone).astimezone(timezone.utc)
    routines = list(
        db.scalars(
            select(Routine)
            .where(Routine.patient_id == patient.id, Routine.is_active.is_(True))
            .order_by(Routine.scheduled_local_time)
        ).all()
    )
    occurrences = {
        item.routine_id: item
        for item in db.scalars(
            select(RoutineOccurrence).where(
                RoutineOccurrence.patient_id == patient.id,
                RoutineOccurrence.scheduled_at_utc >= day_start,
                RoutineOccurrence.scheduled_at_utc <= day_end,
            )
        ).all()
    }
    return [
        {
            "routine_id": routine.id,
            "occurrence_id": occurrences.get(routine.id).id
            if occurrences.get(routine.id)
            else None,
            "title": routine.title,
            "type": routine.type,
            "time_24h": routine.scheduled_local_time.strftime("%H:%M"),
            "status": occurrences.get(routine.id).status
            if occurrences.get(routine.id)
            else "pending",
        }
        for routine in routines
    ]


def _create_voice_routine(
    db: DbSession, patient: Patient, user: CurrentUser, routine_data: dict[str, object]
) -> Routine | None:
    title = str(routine_data.get("title") or "").strip()
    time_24h = str(routine_data.get("time_24h") or "").strip()
    routine_type = str(routine_data.get("type") or "custom").strip()
    if not title or not time_24h:
        return None
    if routine_type not in {
        "medication",
        "appointment",
        "meal",
        "water",
        "spiritual",
        "memory_exercise",
        "conversation",
        "custom",
    }:
        routine_type = "custom"
    try:
        hour_text, minute_text = time_24h.split(":", 1)
        scheduled_time = time(int(hour_text), int(minute_text[:2]))
    except (ValueError, TypeError):
        return None
    try:
        local_zone = ZoneInfo(patient.timezone)
    except ZoneInfoNotFoundError:
        local_zone = timezone.utc
    today = datetime.now(local_zone).date()
    description_raw = routine_data.get("description")
    routine = Routine(
        patient_id=patient.id,
        type=routine_type,
        title=title,
        description=str(description_raw).strip() if description_raw else None,
        timezone=patient.timezone,
        start_date=today,
        recurrence_rule="FREQ=DAILY",
        scheduled_local_time=scheduled_time,
        requires_confirmation=True,
        snooze_minutes=10,
        max_snoozes=2,
        created_by=user.id,
    )
    db.add(routine)
    db.flush()
    if routine_type == "medication":
        medication_raw = routine_data.get("medication")
        medication_data = medication_raw if isinstance(medication_raw, dict) else {}
        medication_name = str(medication_data.get("medication_name") or title).strip()
        dosage_text = str(medication_data.get("dosage_text") or "حسب الوصفة").strip()
        instructions_raw = medication_data.get("instructions")
        db.add(
            MedicationDetail(
                routine_id=routine.id,
                medication_name=medication_name,
                dosage_text=dosage_text,
                instructions=str(instructions_raw).strip() if instructions_raw else None,
            )
        )
        routine.title = medication_name
    scheduled_local = datetime.combine(today, scheduled_time, tzinfo=local_zone)
    db.add(
        RoutineOccurrence(
            routine_id=routine.id,
            patient_id=patient.id,
            scheduled_at_utc=scheduled_local.astimezone(timezone.utc),
            status="pending",
        )
    )
    db.commit()
    db.refresh(routine)
    return routine


def _edit_voice_routine(
    db: DbSession, patient: Patient, user: CurrentUser, parsed: dict[str, object]
) -> Routine | None:
    routine = _find_voice_routine(db, patient, parsed)
    patch = parsed.get("patch")
    if routine is None or not isinstance(patch, dict):
        return None
    require_caregiver_access(db, user, patient.id)
    changed = False
    title = str(patch.get("title") or "").strip()
    if title:
        routine.title = title
        changed = True
    description = patch.get("description")
    if description is not None:
        routine.description = str(description).strip() or None
        changed = True
    scheduled_time = _parse_voice_time(str(patch.get("time_24h") or ""))
    if scheduled_time is not None:
        routine.scheduled_local_time = scheduled_time
        local_zone = _patient_zone(patient)
        for occurrence in db.scalars(
            select(RoutineOccurrence).where(
                RoutineOccurrence.routine_id == routine.id,
                RoutineOccurrence.status.in_(("pending", "reminded", "snoozed")),
            )
        ).all():
            local_day = occurrence.scheduled_at_utc.astimezone(local_zone).date()
            occurrence.scheduled_at_utc = datetime.combine(
                local_day, scheduled_time, tzinfo=local_zone
            ).astimezone(timezone.utc)
        changed = True
    medication_patch = patch.get("medication")
    if routine.type == "medication":
        medication = db.scalar(
            select(MedicationDetail).where(MedicationDetail.routine_id == routine.id)
        )
        if medication is None:
            medication = MedicationDetail(
                routine_id=routine.id,
                medication_name=routine.title,
                dosage_text="حسب الوصفة",
                instructions=None,
            )
            db.add(medication)
        if title:
            medication.medication_name = title
        if isinstance(medication_patch, dict):
            medication_name = str(medication_patch.get("medication_name") or "").strip()
            dosage_text = str(medication_patch.get("dosage_text") or "").strip()
            instructions = medication_patch.get("instructions")
            if medication_name:
                medication.medication_name = medication_name
                routine.title = medication_name
                changed = True
            if dosage_text:
                medication.dosage_text = dosage_text
                changed = True
            if instructions is not None:
                medication.instructions = str(instructions).strip() or None
                changed = True
    if not changed:
        return None
    db.commit()
    db.refresh(routine)
    return routine


def _delete_voice_routine(
    db: DbSession, patient: Patient, user: CurrentUser, parsed: dict[str, object]
) -> str | None:
    routine = _find_voice_routine(db, patient, parsed)
    if routine is None:
        return None
    require_caregiver_access(db, user, patient.id)
    title = routine.title
    routine.is_active = False
    for occurrence in db.scalars(
        select(RoutineOccurrence).where(
            RoutineOccurrence.routine_id == routine.id,
            RoutineOccurrence.status.in_(("pending", "reminded", "snoozed")),
        )
    ).all():
        occurrence.status = "cancelled"
        occurrence.confirmation_source = "caregiver"
    db.commit()
    return title


def _set_voice_occurrence_status(
    db: DbSession,
    patient: Patient,
    user: CurrentUser,
    parsed: dict[str, object],
    *,
    completed: bool,
) -> str | None:
    require_caregiver_access(db, user, patient.id)
    occurrence = _find_voice_occurrence(db, patient, parsed)
    if occurrence is None:
        routine = _find_voice_routine(db, patient, parsed)
        if routine is None:
            return None
        occurrence = _today_occurrence_for_routine(db, patient, routine)
    if occurrence is None or occurrence.status == "cancelled":
        return None
    routine = db.get(Routine, occurrence.routine_id)
    if routine is None or routine.patient_id != patient.id:
        return None
    if completed:
        occurrence.status = "completed"
        occurrence.completed_at = utc_now()
        occurrence.confirmation_source = "patient_voice"
    else:
        occurrence.status = "pending"
        occurrence.completed_at = None
        occurrence.confirmation_source = None
        occurrence.notes = None
    db.commit()
    return routine.title


def _find_voice_occurrence(
    db: DbSession, patient: Patient, parsed: dict[str, object]
) -> RoutineOccurrence | None:
    occurrence_id = str(parsed.get("target_occurrence_id") or "").strip()
    if occurrence_id:
        occurrence = db.get(RoutineOccurrence, occurrence_id)
        if occurrence is not None and occurrence.patient_id == patient.id:
            return occurrence
    routine = _find_voice_routine(db, patient, parsed)
    return _today_occurrence_for_routine(db, patient, routine) if routine else None


def _today_occurrence_for_routine(
    db: DbSession, patient: Patient, routine: Routine
) -> RoutineOccurrence | None:
    local_zone = _patient_zone(patient)
    today = datetime.now(local_zone).date()
    day_start = datetime.combine(today, time.min, tzinfo=local_zone).astimezone(timezone.utc)
    day_end = datetime.combine(today, time.max, tzinfo=local_zone).astimezone(timezone.utc)
    return db.scalar(
        select(RoutineOccurrence)
        .where(
            RoutineOccurrence.patient_id == patient.id,
            RoutineOccurrence.routine_id == routine.id,
            RoutineOccurrence.scheduled_at_utc >= day_start,
            RoutineOccurrence.scheduled_at_utc <= day_end,
        )
        .order_by(RoutineOccurrence.scheduled_at_utc)
    )


def _find_voice_routine(
    db: DbSession, patient: Patient, parsed: dict[str, object]
) -> Routine | None:
    routine_id = str(parsed.get("target_routine_id") or "").strip()
    if routine_id:
        routine = db.get(Routine, routine_id)
        if routine is not None and routine.patient_id == patient.id and routine.is_active:
            return routine
    target_title = str(parsed.get("target_title") or "").strip()
    if not target_title:
        patch = parsed.get("patch")
        if isinstance(patch, dict):
            target_title = str(patch.get("target_title") or "").strip()
    routines = list(
        db.scalars(
            select(Routine).where(
                Routine.patient_id == patient.id,
                Routine.is_active.is_(True),
            )
        ).all()
    )
    if target_title:
        normalized_target = _normalize_voice_text(target_title)
        matches = [
            routine
            for routine in routines
            if normalized_target in _normalize_voice_text(routine.title)
            or _normalize_voice_text(routine.title) in normalized_target
        ]
        if len(matches) == 1:
            return matches[0]
    if len(routines) == 1:
        return routines[0]
    return None


def _parse_voice_time(value: str) -> time | None:
    if not value or ":" not in value:
        return None
    try:
        hour_text, minute_text = value.split(":", 1)
        return time(int(hour_text), int(minute_text[:2]))
    except (TypeError, ValueError):
        return None


def _normalize_voice_text(value: str) -> str:
    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ى": "ي",
        "ة": "ه",
        "ؤ": "و",
        "ئ": "ي",
    }
    normalized = value.strip().lower()
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    return "".join(character for character in normalized if character.isalnum())


def _voice_action_default_text(action: str) -> str:
    return {
        "open_dashboard": "تم، فتحت لك الرئيسية.",
        "open_routine": "تم، فتحت لك الروتين.",
        "open_activities": "تم، فتحت لك النشاط.",
        "open_album": "تم، فتحت لك الألبوم.",
        "open_settings": "تم، فتحت لك الإعدادات.",
        "start_poem_test": "أبشر، بختار لك قصيدة ونتمرّن عليها بهدوء.",
        "start_photo_test": "تم، بفتح لك اختبار الصور.",
        "add_routine": "تم، أضفتها للروتين.",
        "edit_routine": "تم، عدّلت الروتين.",
        "delete_routine": "تم، حذفتها من الروتين.",
        "complete_routine": "تم، علّمتها كمنجزة.",
        "undo_complete_routine": "تم، شلت علامة تم.",
        "unknown": "عذرًا، ما سمعت الكلام كاملًا. هل تسمح تعيده بهدوء؟",
    }.get(action, "تم.")


def _care_preferences(patient: Patient) -> dict[str, str | None]:
    raw = patient.accessibility_preferences_json or {}
    care = raw.get("care_profile") if isinstance(raw, dict) else {}
    return care if isinstance(care, dict) else {}


def _care_profile_response(
    patient: Patient, user: CurrentUser, db: DbSession
) -> CareProfileResponse:
    relationship = None
    if user.role == "caregiver":
        link = db.get(CaregiverPatient, (user.id, patient.id))
        relationship = link.relationship_label if link else None
    care = _care_preferences(patient)
    caregiver_rows = db.execute(
        select(User, CaregiverPatient)
        .join(CaregiverPatient, CaregiverPatient.caregiver_user_id == User.id)
        .where(CaregiverPatient.patient_id == patient.id)
        .order_by(CaregiverPatient.is_primary.desc(), CaregiverPatient.created_at)
    ).all()
    contacts = list(
        db.scalars(
            select(EmergencyContact)
            .where(EmergencyContact.patient_id == patient.id, EmergencyContact.is_active.is_(True))
            .order_by(EmergencyContact.priority_order, EmergencyContact.created_at)
        ).all()
    )
    recipients = [
        AlertRecipientResponse(
            id=caregiver.id,
            name=caregiver.full_name,
            relationship=link.relationship_label,
            email=caregiver.email,
            phone=caregiver.phone,
            source="family_account",
        )
        for caregiver, link in caregiver_rows
    ] + [
        AlertRecipientResponse(
            id=contact.id,
            name=contact.name,
            relationship=contact.relationship,
            email=contact.email,
            phone=contact.phone,
            source="emergency_contact",
        )
        for contact in contacts
    ]
    return CareProfileResponse(
        patient_id=patient.id,
        display_name=patient.display_name,
        relationship_label=relationship,
        likes=care.get("likes"),
        dislikes=care.get("dislikes"),
        disease_stage=care.get("disease_stage"),
        care_description=care.get("care_description"),
        condition_notes=patient.condition_notes,
        alert_recipients=recipients,
        emergency_contacts=[EmergencyContactResponse.model_validate(item) for item in contacts],
    )


@router.get("/patients/{patient_id}/care-profile", response_model=CareProfileResponse)
def get_care_profile(patient_id: str, user: CurrentUser, db: DbSession) -> CareProfileResponse:
    require_patient_access(db, user, patient_id)
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return _care_profile_response(patient, user, db)


@router.patch("/patients/{patient_id}/care-profile", response_model=CareProfileResponse)
def update_care_profile(
    patient_id: str, request: CareProfileUpdate, user: CurrentUser, db: DbSession
) -> CareProfileResponse:
    require_caregiver_access(db, user, patient_id)
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    if request.condition_notes is not None:
        patient.condition_notes = request.condition_notes.strip() or None
    if request.relationship_label is not None:
        link = db.get(CaregiverPatient, (user.id, patient_id))
        if link is not None:
            link.relationship_label = request.relationship_label.strip() or "family"
    preferences = dict(patient.accessibility_preferences_json or {})
    care = dict(_care_preferences(patient))
    for key in ("likes", "dislikes", "disease_stage", "care_description"):
        value = getattr(request, key)
        if value is not None:
            care[key] = value.strip() or None
    preferences["care_profile"] = care
    patient.accessibility_preferences_json = preferences
    db.commit()
    db.refresh(patient)
    return _care_profile_response(patient, user, db)


@router.post(
    "/patients/{patient_id}/emergency-contacts",
    response_model=EmergencyContactResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_emergency_contact(
    patient_id: str, request: EmergencyContactCreate, user: CurrentUser, db: DbSession
) -> EmergencyContactResponse:
    require_caregiver_access(db, user, patient_id)
    priority = (
        db.scalar(
            select(func.max(EmergencyContact.priority_order)).where(
                EmergencyContact.patient_id == patient_id
            )
        )
        or 0
    ) + 1
    contact = EmergencyContact(
        patient_id=patient_id,
        name=request.name.strip(),
        relationship=request.relationship.strip(),
        phone=request.phone.strip() if request.phone else "",
        email=request.email.strip() if request.email else None,
        priority_order=priority,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return EmergencyContactResponse.model_validate(contact)


@router.delete("/emergency-contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_emergency_contact(contact_id: str, user: CurrentUser, db: DbSession) -> None:
    contact = db.get(EmergencyContact, contact_id)
    if contact is None or not contact.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    require_caregiver_access(db, user, contact.patient_id)
    contact.is_active = False
    db.commit()
