"""Pydantic v2 data models for the wargame event stream.

Every simulation event is a self-contained ``GameEvent`` written as one JSONL
line.  The TUI, stores, and any downstream consumer all derive from this model.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Discriminator for the event stream."""

    GAME_START = "game_start"
    SITUATION_REPORT = "situation_report"
    LLM_DECISION = "llm_decision"
    STATE_CHANGE = "state_change"
    KPI_UPDATE = "kpi_update"
    PHASE_TRANSITION = "phase_transition"
    ANNOTATION = "annotation"  # legacy alias — kept for backward compat with old JSONL files
    TAG = "tag"
    GAME_END = "game_end"


class EventSource(str, Enum):
    """Who produced this event — critical for attribution in the TUI."""

    SIMULATION = "simulation"
    LLM = "llm"
    HUMAN = "human"
    SYSTEM = "system"


class GameEvent(BaseModel):
    """Single event in the simulation stream.  One line in JSONL output."""

    model_config = {"frozen": True}

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_id: Optional[str] = None
    sequence_number: int
    turn_number: int
    phase: str = ""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    event_type: EventType
    source: EventSource
    source_detail: str = ""

    title: str
    body: str = ""
    structured_data: dict[str, Any] = Field(default_factory=dict)

    content_hash: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.content_hash:
            h = hashlib.sha256(f"{self.body}:{self.sequence_number}".encode()).hexdigest()[:16]
            object.__setattr__(self, "content_hash", h)
