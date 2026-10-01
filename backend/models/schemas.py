from pydantic import BaseModel, Field
from typing import Optional

class BugCreate(BaseModel):
    title: str
    description: str
    repository: str = "demo_repo"
    reporter: str = "tester"

class FeedbackCreate(BaseModel):
    feedback: str = Field(min_length=1)
    developer: str = "developer"

class BugOut(BaseModel):
    id: int
    title: str
    description: str
    repository: str
    reporter: str
    status: str
    current_iteration: int
    root_cause: str
    relevant_files: list[str]
    created_at: str
    updated_at: str
    resolved_at: Optional[str] = None

class ActionResult(BaseModel):
    ok: bool
    message: str
