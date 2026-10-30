"""Runs one LLM step: versioned prompt -> call -> JSON schema validation -> one repair retry -> audit + cost cap."""
import json

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.core.costs import check_cap
from app.db.models import AuditLog, Task
from app.guards.redaction import redact
from app.llm.base import LLMClient, LLMError, extract_json, load_prompt


class StepFailed(Exception):
    pass


def audit(db: Session, task_id: int | None, step: str, *, model=None, prompt_hash=None, input_text=None,
          output=None, tokens_in=0, tokens_out=0, cost=0.0, latency=0.0, result=None) -> None:
    db.add(AuditLog(task_id=task_id, step=step, model=model, prompt_hash=prompt_hash,
                    input_redacted=redact(input_text)[:2000] if input_text else None,
                    output=(output or "")[:2000] or None, tokens_in=tokens_in, tokens_out=tokens_out,
                    cost_inr=cost, latency_ms=round(latency, 2), validator_result=result))


class Runner:
    def __init__(self, db: Session, llm: LLMClient, task: Task | None = None):
        self.db, self.llm, self.task = db, llm, task

    def run(self, step: str, payload: dict, schema: type[BaseModel], tier: str = "small") -> BaseModel:
        system, phash = load_prompt(step)
        task_id = self.task.id if self.task else None
        error = None
        for attempt in (0, 1):
            body = dict(payload)
            if error:
                body["repair"] = f"Previous output was invalid: {error}. Return valid JSON only."
            user = json.dumps(body, ensure_ascii=False)
            try:
                resp = self.llm.complete(step, system, user, tier)
            except LLMError as e:
                audit(self.db, task_id, step, prompt_hash=phash, input_text=user, result=f"llm_error:{e}"[:190])
                raise StepFailed(f"{step}: {e}") from e
            if self.task is not None:
                self.task.llm_cost_inr = round((self.task.llm_cost_inr or 0) + resp.cost_inr, 5)
            try:
                parsed = schema.model_validate(extract_json(resp.text))
                result = "ok" if attempt == 0 else "ok_after_repair"
                error = None
            except (ValidationError, LLMError) as e:
                parsed, error = None, str(e)[:160].replace("\n", " ")
                result = f"invalid:{error}"[:190]
            audit(self.db, task_id, step, model=resp.model, prompt_hash=phash, input_text=user, output=resp.text,
                  tokens_in=resp.tokens_in, tokens_out=resp.tokens_out, cost=resp.cost_inr,
                  latency=resp.latency_ms, result=result)
            if self.task is not None:
                check_cap(self.task.llm_cost_inr)
            if parsed is not None:
                return parsed
        raise StepFailed(f"{step}: invalid output after repair ({error})")
