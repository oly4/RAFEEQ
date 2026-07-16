from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ActivityCreate(BaseModel):
    type: Literal[
        "recognize_photos",
        "complete_phrase",
        "calm_music",
        "conversation",
        "reading",
        "memory_exercise",
        "poem_completion",
        "custom",
    ]
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    instructions: str | None = Field(default=None, max_length=2000)
    duration_minutes: int | None = Field(default=None, ge=1, le=240)


class ActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    patient_id: str
    type: str
    title: str
    description: str | None
    instructions: str | None
    duration_minutes: int | None
    is_active: bool


class ActivityList(BaseModel):
    items: list[ActivityResponse]
    page: int = 1
    page_size: int = 20
    total: int


class ActivityLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    activity_id: str
    patient_id: str
    started_at: datetime
    completed_at: datetime | None
    status: str
    completion_source: str | None


class PoemSpeechRequest(BaseModel):
    poem_start: str = Field(min_length=1, max_length=1200)


class PoemSpeechResponse(BaseModel):
    prompt_text: str
    audio_data_url: str | None = None
    used_openai: bool = False


class PoemVoiceTestRequest(BaseModel):
    poem_start: str = Field(min_length=1, max_length=1200)
    expected_completion: str = Field(min_length=1, max_length=1200)
    audio_data_url: str = Field(min_length=1, max_length=16_000_000)


class PoemVoiceTestResponse(BaseModel):
    transcript: str = ""
    matched: bool
    assistant_text: str
    hint_text: str | None = None
    audio_data_url: str | None = None
    used_openai: bool = False


class SavedPoemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    poem_start: str = Field(min_length=1, max_length=1200)
    expected_completion: str = Field(min_length=1, max_length=1200)


class SavedPoemResponse(BaseModel):
    id: str
    title: str
    poem_start: str
    expected_completion: str
