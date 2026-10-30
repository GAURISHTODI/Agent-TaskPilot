from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.agents.taxonomy import BY_NAME


class ClassifyOut(BaseModel):
    category: str
    confidence: float = Field(ge=0, le=1)

    @field_validator("category")
    @classmethod
    def known(cls, v: str) -> str:
        if v != "unknown" and v not in BY_NAME:
            raise ValueError(f"category {v!r} not in taxonomy")
        return v


class ClarifyOut(BaseModel):
    question: str = Field(min_length=5)


class ToolReq(BaseModel):
    tool: str


class PlanStep(BaseModel):
    order: int
    owner: Literal["agent", "human", "vendor"]
    action: str
    effort_min: float = Field(ge=0)


class PlanOut(BaseModel):
    steps: list[PlanStep] = Field(min_length=1)
    tool_requests: list[ToolReq] = []


class RiskOut(BaseModel):
    risk: float = Field(ge=0, le=1)
    reasons: list[str] = []


class DraftOut(BaseModel):
    draft: str


class ReplyOut(BaseModel):
    available: bool | None = None
    price: int | None = None
    slot: str | None = None
    notes: str = ""
    tool_requests: list[ToolReq] = []


class JudgeOut(BaseModel):
    faithfulness: int = Field(ge=1, le=5)  # every fact in the draft is supported; nothing invented
    completeness: int = Field(ge=1, le=5)  # all provided facts are conveyed
    tone: int = Field(ge=1, le=5)          # courteous, concise, brand-appropriate
