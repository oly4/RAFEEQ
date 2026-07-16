from typing import Protocol


class SpeakerAdapter(Protocol):
    def speak(self, text: str, locale: str = "ar") -> None: ...


class VoiceInputAdapter(Protocol):
    def listen_text(self, timeout_seconds: int = 15) -> str | None: ...


class SosButtonAdapter(Protocol):
    def is_pressed(self) -> bool: ...


class NetworkAdapter(Protocol):
    def is_online(self) -> bool: ...
