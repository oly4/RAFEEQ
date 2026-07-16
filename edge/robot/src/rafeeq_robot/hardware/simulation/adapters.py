def format_console_text(text: str) -> str:
    if any("\u0600" <= character <= "\u06ff" for character in text):
        return f"\u202b{text}\u202c"
    return text


def clean_speech_text(text: str) -> str:
    return "".join(
        character
        for character in text
        if character
        not in {
            "\u200e",
            "\u200f",
            "\u202a",
            "\u202b",
            "\u202c",
            "\u202d",
            "\u202e",
            "\ufeff",
        }
    )


class ConsoleSpeaker:
    def speak(self, text: str, locale: str = "ar") -> None:
        print(f"[{locale}] {format_console_text(text)}")


class SimulatedNetwork:
    def __init__(self, online: bool = True) -> None:
        self.online = online

    def is_online(self) -> bool:
        return self.online
