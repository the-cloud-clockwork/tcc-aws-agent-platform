"""Pydantic models for prompt registry."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class PromptStatus(str, Enum):
    DRAFT = "draft"
    STABLE = "stable"
    DEPRECATED = "deprecated"


class PromptVersion(BaseModel):
    """Stored metadata for a prompt version (maps to DynamoDB item)."""

    model_config = ConfigDict(populate_by_name=True)

    prompt_id: str = Field(alias="prompt_key")
    version: str
    description: str = ""
    status: PromptStatus = PromptStatus.DRAFT
    s3_key: str = ""
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    tags: list[str] = Field(default_factory=list)


class PromptCreateRequest(BaseModel):
    """Payload for POST /prompts."""

    prompt_id: str
    version: str
    content: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class PromptPromoteRequest(BaseModel):
    """Payload for POST /prompts/{prompt_id}/promote."""

    version: str


class PromptRollbackRequest(BaseModel):
    """Payload for POST /prompts/{prompt_id}/rollback."""

    version: str


class PromptResolveResponse(BaseModel):
    """Response when resolving a prompt ref."""

    prompt_id: str
    version: str
    content: str
    status: PromptStatus


class PromptVersionListItem(BaseModel):
    """Item in version list response."""

    model_config = ConfigDict(populate_by_name=True)

    prompt_id: str = Field(alias="prompt_key")
    version: str
    description: str
    status: PromptStatus
    created_at: str
    tags: list[str] = Field(default_factory=list)


class Mode(str, Enum):
    """Execution environment that controls draft prompt visibility."""

    SIMULATION = "simulation"
    DEV = "dev"
    STAGING = "staging"
    PRODUCTION = "production"


# Modes where draft prompts are visible
DRAFT_ALLOWED_MODES: set[Mode] = {Mode.SIMULATION, Mode.DEV}
