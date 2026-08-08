from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DiagnosticStartRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    book_id: str = Field(alias="bookId")
    learning_goal: str = Field(default="", alias="learningGoal")
    user_id: str = Field(default="user_001", alias="userId")


class DiagnosticAnswerRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    question_id: str = Field(alias="questionId")
    answer: str = ""
    skipped: bool = False


class DiagnosticCalibrationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    diagnostic_id: str = Field(alias="diagnosticId")
    level: str
    reason: str = ""
