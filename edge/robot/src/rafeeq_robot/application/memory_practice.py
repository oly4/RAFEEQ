from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

import httpx

from rafeeq_robot.application.language import choose_locale_text, detect_spoken_locale
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

    def hint_for_locale(self, locale: str) -> str:
        if self.spoken_prompt:
            return self.spoken_prompt
        if self.description:
            return self.description
        if self.people_labels:
            first = self.people_labels[0].split()
            if first:
                return choose_locale_text(
                    locale,
                    f"تبدأ بـ {first[0]}",
                    f"It starts with {first[0]}",
                )
        return choose_locale_text(
            locale,
            "حاول تتذكر الاسم أو المناسبة.",
            "Try to remember the name or the occasion.",
        )


class MemoryPracticeService:
    """Voice-driven saved album/photo memory tour."""

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
        _ = voice_input
        query = _extract_memory_query(transcript)
        if query is None:
            return False

        locale = detect_spoken_locale(transcript)
        memories = self._load_saved_memories()
        if not memories:
            message = choose_locale_text(
                locale,
                "ما لقيت ذكريات محفوظة في الألبوم.",
                "I could not find saved memories in the album.",
            )
            self._record_action(transcript, message)
            self.speaker.speak(
                choose_locale_text(
                    locale,
                    "ما لقيت ذكريات محفوظة في الألبوم. أضف صور أو ذكريات من التطبيق، وبعدها أعرضها بهدوء.",
                    "I could not find saved memories in the album. Add photos or memories "
                    "from the app, then I can show them gently.",
                ),
                locale,
            )
            return True

        ordered_memories = self._ordered_memories_for_tour(memories, query, locale)
        action_text = choose_locale_text(
            locale,
            "أبشر، نبدأ جولة الذكريات. بعرض الصور وأقرأ وصفها بهدوء.",
            "Sure. Let’s start the memory tour. I will show the photos and describe them gently.",
        )
        self._record_action(
            transcript,
            action_text,
            {
                "memory_count": len(ordered_memories),
                "memory_titles": [memory.title for memory in ordered_memories],
            },
        )
        self.speaker.speak(action_text, locale)
        for index, memory in enumerate(ordered_memories, start=1):
            _wait_until_done_speaking(self.speaker)
            narration = _memory_narration(memory, locale)
            print(
                "Memory tour "
                f"{index}/{len(ordered_memories)}: {format_console_text(memory.title)}"
            )
            self._record_memory_tour_item(memory, transcript, narration, index)
            self.speaker.speak(
                choose_locale_text(
                    locale,
                    f"الصورة {index} من {len(ordered_memories)}. {narration}",
                    f"Photo {index} of {len(ordered_memories)}. {narration}",
                ),
                locale,
            )
        _wait_until_done_speaking(self.speaker)
        self.speaker.speak(
            choose_locale_text(
                locale,
                "انتهت جولة الذكريات. نقدر نعيدها وقت ما تحب.",
                "The memory tour is finished. We can replay it anytime.",
            ),
            locale,
        )
        return True

    def _ordered_memories_for_tour(
        self,
        memories: list[MemoryPrompt],
        query: str,
        locale: str,
    ) -> list[MemoryPrompt]:
        if not memories:
            return []
        normalized_query = _normalize_text(query)
        if not normalized_query:
            return _locale_first_order(memories, locale)
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
        if score < 0.35:
            return _locale_first_order(memories, locale)
        return [memory, *[item for item in memories if item is not memory]]

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

    def _record_memory_tour_item(
        self,
        memory: MemoryPrompt,
        transcript: str,
        assistant_text: str,
        index: int,
    ) -> None:
        self.outbox.record(
            "voice_memory_tour",
            {
                "memory_id": memory.id,
                "memory_title": memory.title,
                "transcript": transcript,
                "assistant_text": assistant_text,
                "index": index,
            },
        )


def _extract_memory_query(transcript: str) -> str | None:
    normalized = _normalize_text(transcript)
    if not normalized:
        return None
    trigger_patterns = (
        r"(?:جوله|جولة)\s*(?:ال)?(?:ذكريات|ذاكره|ذاكرة|البوم|ألبوم|الالبوم|الصور)\s*(.*)",
        r"(?:ابد[اأ]?\s*)?(?:اختبار|تمرين)?\s*(?:ال)?(?:البوم|ألبوم|الالبوم|الصور|صوره|صورة|ذاكره|ذاكرة)\s*(.*)",
        r"(?:اختبرني|دربني)\s*(?:في|على|ب)?\s*(?:ال)?(?:البوم|ألبوم|الصور|صوره|صورة|ذاكره|ذاكرة)\s*(.*)",
        r"(?:start|begin|run|open|show)\s+(?:the\s+)?(?:album|photos|photo|pictures|picture|memories|memory)\s*(?:tour|test|practice)?\s*(.*)",
        r"(?:memory|album|photo|picture)\s+tour\s*(.*)",
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


def _memory_narration(memory: MemoryPrompt, locale: str) -> str:
    if memory.spoken_prompt.strip():
        return memory.spoken_prompt.strip()
    if memory.description.strip():
        return memory.description.strip()
    if memory.people_labels:
        joined = choose_locale_text(
            locale,
            " و ".join(memory.people_labels),
            " and ".join(memory.people_labels),
        )
        return choose_locale_text(
            locale,
            f"هذه ذكرى جميلة مع {joined}.",
            f"This is a warm memory with {joined}.",
        )
    if memory.title.strip():
        return choose_locale_text(
            locale,
            f"هذه ذكرى عن {memory.title}.",
            f"This memory is about {memory.title}.",
        )
    return choose_locale_text(
        locale,
        "هذه صورة من الذكريات الجميلة.",
        "This is a gentle memory photo.",
    )


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


def _first_locale_match(memories: list[MemoryPrompt], locale: str) -> MemoryPrompt | None:
    for memory in memories:
        text = " ".join(
            (
                memory.title,
                memory.description,
                memory.spoken_prompt,
                " ".join(memory.people_labels),
            )
        )
        if detect_spoken_locale(text) == locale:
            return memory
    return None


def _locale_first_order(memories: list[MemoryPrompt], locale: str) -> list[MemoryPrompt]:
    preferred = _first_locale_match(memories, locale)
    if preferred is None:
        return memories
    return [preferred, *[memory for memory in memories if memory is not preferred]]


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
