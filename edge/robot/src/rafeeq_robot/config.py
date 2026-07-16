from pydantic_settings import BaseSettings, SettingsConfigDict


class RobotSettings(BaseSettings):
    rafeeq_device_id: str = "00000000-0000-0000-0000-000000000001"
    rafeeq_device_secret: str = ""
    rafeeq_patient_id: str = "00000000-0000-0000-0000-000000000002"
    backend_base_url: str = "http://127.0.0.1:8000"
    hardware_mode: str = "simulation"
    speaker_provider: str = "console"
    audio_output_device: int | None = None
    speaker_rate: int = 0
    speaker_volume: int = 100
    piper_voice_model: str = "./.run/models/piper/ar_JO-kareem-medium/ar_JO-kareem-medium.onnx"
    piper_voice_config: str = (
        "./.run/models/piper/ar_JO-kareem-medium/ar_JO-kareem-medium.onnx.json"
    )
    local_database_path: str = "./data/robot.db"
    fall_verification_timeout_seconds: int = 20
    fall_detection_cooldown_seconds: int = 60
    voice_interaction_provider: str = "simulation"
    vosk_model_path: str = "./.run/models/vosk-ar"
    vosk_input_device: int | str | None = None
    vosk_sample_rate: int = 16000
    voice_listen_seconds: int = 15
    voice_reasoning_provider: str = "local"
    openai_api_key: str = ""
    openai_realtime_model: str = "gpt-realtime-2.1-mini"
    openai_text_model: str = "gpt-5.4-nano"
    openai_reasoning_effort: str = "medium"
    openai_transcription_model: str = "gpt-4o-mini-transcribe"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "alloy"
    rafeeq_voice_access_token: str = ""
    rafeeq_voice_caregiver_email: str = ""
    rafeeq_voice_caregiver_password: str = ""
    voice_max_session_seconds: int = 120
    voice_reminder_snooze_minutes: int = 10
    voice_upload_audio: bool = False
    voice_silence_threshold: int = 24
    voice_confirm_before_response: bool = False
    voice_wake_word_required: bool = False
    voice_wake_words: str = "يا رفيق,يارفيق,رفيق,رافع,rafeeq,rafeeq"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=(".env", ".env.robot"), extra="ignore")
