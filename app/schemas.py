from typing import Any

from pydantic import BaseModel, Field, field_validator


class RegionRequest(BaseModel):
    region: str = Field(..., min_length=1)

    @field_validator("region")
    @classmethod
    def strip_region(cls, value: str) -> str:
        return value.strip()


class ApiResponse(BaseModel):
    ok: bool
    data: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
