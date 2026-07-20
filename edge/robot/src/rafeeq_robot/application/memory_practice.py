from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

import httpx

from rafeeq_robot.application.outbox_service import OutboxService
from rafeeq_robot.config import RobotSettings
from rafeeq_robot.hardware.interfaces import SpeakerAdapter, VoiceInputAdapter
from rafeeq_robot.hardware.simulation.adapters import format_console_text


@dataclass(frozen=True)
class MemoryPrompt:
    id: str
    title: str
    description: str
    media_type: str
    object_key_or_url: str
    people_labels: tuple[str, ...]
    spoken_prompt: str

    @property
    def accepted_answers(self) -> tuple[str, ...]:
        answers = [self.title, *self.people_labels]
        return tuple(answer for answer in answers if answer.strip())

    @property
    def hint(self) -> str:
        if self.spoken_prompt:
            return self.spoken_prompt
        if self.description:
            return self.description
        if self.people_labels:
            first = self.people_labels[0].split()
            if first:
                return f"تبدأ بـ {first[0]}"
        return "حاول تتذكر الاسم أو المناسبة."


class MemoryPracticeService:
    """Voice-driven saved album/photo memory test."""

    def __init__(
        self,
        settings: RobotSettings,
        outbox: OutboxService,
        speaker: SpeakerAdapter,
    ) -> None:
        self.settings = settings
        self.outbox = outbox
        self.speaker = speaker
        self._access_token = settings.rafeeq_voice_access_token.strip()

    def can_handle(self, transcript: str) -> bool:
        return _extract_memory_query(transcript) is not None

    def handle_text(self, transcript: str, voice_input: VoiceInputAdapter) -> bool:
        query = _extract_memory_query(transcript)
        if query is None:
            return False

        memory = self._select_memory(query)
        if memory is None:
            self._record_action(transcript, "ما لقيت ذكريات محفوظة في الألبوم.")
            self.speaker.speak(
                "ما لقيت ذكريات محفوظة في الألبوم. أضف صور أو ذكريات من التطبيق، وبعدها أختبرك فيها.",
                "ar",
            )
            return True

        self._record_action(
            transcript,
            f"نبدأ اختبار الذاكرة: {memory.title}.",
            {
                "memory_id": memory.id,
                "memory_title": memory.title,
                "media_type": memory.media_type,
            },
        )
        if memory.media_type == "photo":
            intro = f"أبشر. بفتح لك صورة {memory.title} في الألبوم، وراح أسألك عنها."
        else:
            intro = f"أبشر. نبدأ اختبار ذكرى {memory.title}."
        self.speaker.speak(intro, "ar")
        prompt = memory.spoken_prompt or memory.description
        if prompt:
            self.speaker.speak(prompt, "ar")
        self.speaker.speak("من تتذكر في هذه الذكرى؟", "ar")

        for attempt in range(1, 3):
            if attempt == 2:
                self.speaker.speak(f"تلميح: {memory.hint}. جرّب مرة ثانية.", "ar")
            _wait_until_done_speaking(self.speaker)
            answer = voice_input.listen_text(max(6, self.settings.voice_listen_seconds))
            if answer:
                print(f"Memory answer attempt {attempt}: {format_console_text(answer)}")
            else:
                print(f"Memory answer attempt {attempt}: <no speech>")
            matched = bool(answer and _is_matching_memory_answer(answer, memory))
            self._record_memory_result(memory, transcript, answer or "", matched, attempt)
            if matched:
                self.speaker.speak("صح عليك، هذا تذكر جميل.", "ar")
                return True

        expected = " أو ".join(memory.accepted_answers[:3]) or memory.title
        self.speaker.speak(
            f"ولا يهمك. الإجابة المتوقعة كانت: {expected}. نعيدها وقت ما تحب.",
            "ar",
        )
        return True

    def _select_memory(self, query: str) -> MemoryPrompt | None:
        memories = self._load_saved_memories()
        if not memories:
            return None
        normalized_query = _normalize_text(query)
        if not normalized_query:
            return memories[0]
        scored = [
            (
                max(
                    SequenceMatcher(None, normalized_query, _normalize_text(memory.title)).ratio(),
                    1.0 if normalized_query in _normalize_text(memory.title) else 0.0,
                    max(
                        (
                            SequenceMatcher(
                                None,
                                normalized_query,
                                _normalize_text(label),
                            ).ratio()
                            for label in memory.people_labels
                        ),
                        default=0.0,
                    ),
                ),
                memory,
            )
            for memory in memories
        ]
        score, memory = max(scored, key=lambda item: item[0])
        return memory if score >= 0.35 else memories[0]

    def _load_saved_memories(self) -> list[MemoryPrompt]:
        device_memories = self._load_device_saved_memories()
        if device_memories:
            return device_memories
        token = self._get_access_token()
        if not token:
            return []
        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(
                    (
                        f"{self.settings.backend_base_url.rstrip('/')}"
                        f"/api/v1/patients/{self.settings.rafeeq_patient_id}/memories"
                    ),
                    headers={"Authorization": f"Bearer {token}"},
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            print(f"Could not load saved memories from backend: {exc}")
            return []
        return _memories_from_payload(data)

    def _load_device_saved_memories(self) -> list[MemoryPrompt]:
        if not self.settings.rafeeq_device_secret:
            return []
        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(
                    f"{self.settings.backend_base_url.rstrip('/')}/device-api/v1/memories",
                    headers={
                        "X-Device-Id": self.settings.rafeeq_device_id,
                        "X-Device-Secret": self.settings.rafeeq_device_secret,
                    },
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            print(f"Could not load device memories from backend; trying voice auth: {exc}")
            return []
        return _memories_from_payload(data)

    def _get_access_token(self) -> str:
        if self._access_token:
            return self._access_token
        email = self.settings.rafeeq_voice_caregiver_email.strip()
        password = self.settings.rafeeq_voice_caregiver_password.strip()
        if not email or not password:
            return ""
        try:
            with httpx.Client(timeout=10) as client:
                response = client.post(
                    f"{self.settings.backend_base_url.rstrip('/')}/api/v1/auth/login",
                    json={"email": email, "password": password},
                )
                response.raise_for_status()
                token = str(response.json().get("access_token") or "").strip()
        except Exception as exc:
            print(f"Could not authenticate memory voice client: {exc}")
            return ""
        self._access_token = token
        return token

    def _record_action(
        self,
        transcript: str,
        assistant_text: str,
        extra: dict[str, object] | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "action": "start_photo_test",
            "transcript": transcript,
            "assistant_text": assistant_text,
            "used_openai": False,
        }
        if extra:
            payload.update(extra)
        self.outbox.record("voice_app_action", payload)

    def _record_memory_result(
        self,
        memory: MemoryPrompt,
        transcript: str,
        answer: str,
        matched: bool,
        attempt: int,
    ) -> None:
        self.outbox.record(
            "voice_memory_practice",
            {
                "memory_id": memory.id,
                "memory_title": memory.title,
                "transcript": transcript,
                "answer_transcript": answer,
                "matched": matched,
                "attempt": attempt,
            },
        )


def _extract_memory_query(transcript: str) -> str | None:
    normalized = _normalize_text(transcript)
    if not normalized:
        return None
    trigger_patterns = (
        r"(?:ابد[اأ]?\s*)?(?:اختبار|تمرين)?\s*(?:ال)?(?:البوم|ألبوم|الالبوم|الصور|صوره|صورة|ذاكره|ذاكرة)\s*(.*)",
        r"(?:اختبرني|دربني)\s*(?:في|على|ب)?\s*(?:ال)?(?:البوم|ألبوم|الصور|صوره|صورة|ذاكره|ذاكرة)\s*(.*)",
        r"(?:start|begin|run|open)\s+(?:the\s+)?(?:album|photo|picture|memory)\s*(?:test|practice)?\s*(.*)",
        r"(?:album|photo|picture|memory)\s+(?:test|practice|quiz)\s*(.*)",
    )
    for pattern in trigger_patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _is_matching_memory_answer(answer: str, memory: MemoryPrompt) -> bool:
    normalized_answer = _normalize_text(answer)
    if not normalized_answer:
        return False
    for expected in memory.accepted_answers:
        normalized_expected = _normalize_text(expected)
        if not normalized_expected:
            continue
        if (
            normalized_answer in normalized_expected
            or normalized_expected in normalized_answer
            or SequenceMatcher(None, normalized_answer, normalized_expected).ratio() >= 0.72
        ):
            return True
    return False


def _wait_until_done_speaking(speaker: SpeakerAdapter) -> None:
    is_speaking = getattr(speaker, "is_speaking", None)
    while callable(is_speaking) and is_speaking():
        time.sleep(0.1)


def _normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ى": "ي",
        "ة": "ه",
        "ؤ": "و",
        "ئ": "ي",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = re.sub(r"[^\w\s\u0600-\u06FF]", " ", text.lower())
    return " ".join(text.split())


def _memories_from_payload(data: object) -> list[MemoryPrompt]:
    raw_items = data.get("items", data) if isinstance(data, dict) else data
    if not isinstance(raw_items, list):
        return []
    memories: list[MemoryPrompt] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        people = item.get("people_labels_json") or item.get("people_labels") or []
        if not isinstance(people, list):
            people = []
        memories.append(
            MemoryPrompt(
                id=str(item.get("id") or "").strip(),
                title=title,
                description=str(item.get("description") or "").strip(),
                media_type=str(item.get("media_type") or "").strip(),
                object_key_or_url=str(item.get("object_key_or_url") or "").strip(),
                people_labels=tuple(str(label).strip() for label in people if str(label).strip()),
                spoken_prompt=str(item.get("spoken_prompt") or "").strip(),
            )
        )
    return memories
