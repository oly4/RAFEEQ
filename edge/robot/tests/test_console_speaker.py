from io import StringIO

from rafeeq_robot.hardware.simulation.adapters import ConsoleSpeaker


def test_console_speaker_preserves_arabic_text(monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr("sys.stdout", output)
    ConsoleSpeaker().speak("رفيق جاهز")
    assert "رفيق جاهز" in output.getvalue()
