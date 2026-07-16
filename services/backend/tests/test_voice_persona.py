from rafeeq_backend.modules.activities.api.router import (
    _sanitize_voice_assistant_text as sanitize_activity_voice,
)
from rafeeq_backend.modules.memories.api.router import (
    _sanitize_voice_assistant_text as sanitize_memory_voice,
)
from rafeeq_backend.modules.patients.api.router import (
    _sanitize_voice_assistant_text as sanitize_patient_voice,
)


def test_voice_persona_removes_overly_intimate_phrases() -> None:
    text = "أبشر يا الغالي، حبيبي خلنا نحاول مرة ثانية طال عمرك."
    for sanitize in (sanitize_activity_voice, sanitize_memory_voice, sanitize_patient_voice):
        cleaned = sanitize(text)
        assert "يا الغالي" not in cleaned
        assert "حبيبي" not in cleaned
        assert "طال عمرك" not in cleaned
        assert "أبشر" in cleaned
