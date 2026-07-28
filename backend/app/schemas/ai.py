"""AI-related Pydantic schemas."""

from pydantic import BaseModel


class AgentResult(BaseModel):
    """Result from a CodeAgent operation."""

    success: bool
    final_message: str = ""
    iterations: int = 0
    modified_files: list[str] = []
    errors: list[str] = []


class Suggestion(BaseModel):
    """A single improvement suggestion from diagnosis."""

    priority: str = "medium"  # "high", "medium", "low"
    method: str = ""
    reason: str = ""
    evidence: list[str] = []
    expected_improvement: str = ""
    code_changes: dict[str, str] = {}


class Diagnosis(BaseModel):
    """Full diagnosis result from Diagnostician."""

    problem_analysis: str = ""
    suggestions: list[Suggestion] = []
    top_recommendation_index: int = 0


class DialogQuestion(BaseModel):
    """A single question in the brainstorm dialog."""

    question: str
    options: list[str] = []
    type: str = "text"  # "single", "multi", "text"
    finalize: bool = False


class ProjectConfig(BaseModel):
    """Project configuration collected from the brainstorm dialog."""

    improvement_targets: list[str] = []
    target_metrics: dict[str, float] = {}
    max_iterations: int = 5
    summary: str = ""