from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MemoryCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    sort_order: int = Field(default=0, ge=0, le=1000)


class MemoryCategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    patient_id: str
    name: str
    sort_order: int


class MemoryItemCreate(BaseModel):
    category_id: str
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    media_type: Literal["photo", "video", "audio", "text"] = "text"
    object_key_or_url: str | None = Field(default=None, max_length=1000)
    upload_data_url: str | None = Field(default=None, max_length=16_000_000)
    capture_date: date | None = None
    people_labels: list[str] = Field(default_factory=list, max_length=30)
    spoken_prompt: str | None = Field(default=None, max_length=1000)
    visibility: Literal["caregivers", "assigned_doctors", "private"] = "caregivers"


class MemoryItemUpdate(BaseModel):
    category_id: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    people_labels: list[str] | None = Field(default=None, max_length=30)
    spoken_prompt: str | None = Field(default=None, max_length=1000)
    visibility: Literal["caregivers", "assigned_doctors", "private"] | None = None


class MemoryItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    patient_id: str
    category_id: str
    title: str
    description: str | None
    media_type: str
    object_key_or_url: str | None
    capture_date: date | None
    people_labels_json: list[str]
    spoken_prompt: str | None
    visibility: str
    created_at: datetime


class MemoryList(BaseModel):
    items: list[MemoryItemResponse]
    page: int = 1
    page_size: int = 20
    total: int


class MemoryAiTestRequest(BaseModel):
    answer_text: str = Field(default="", max_length=500)


class MemoryAiTestResponse(BaseModel):
    matched: bool
    assistant_text: str
    hint_text: str | None = None
    used_openai: bool = False


class MemoryAiSpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=600)


class MemoryAiSpeechResponse(BaseModel):
    assistant_text: str
    audio_data_url: str | None = None
    used_openai: bool = False


class MemoryAiVoiceTestRequest(BaseModel):
    audio_data_url: str = Field(min_length=1, max_length=16_000_000)


class MemoryAiVoiceTestResponse(MemoryAiTestResponse):
    transcript: str = ""
    audio_data_url: str | None = None
