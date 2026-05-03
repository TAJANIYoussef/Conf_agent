from pydantic import BaseModel, Field
from typing import Optional
from datetime import date

class Conference(BaseModel):
    name: str
    acronym: str
    url: str
    conference_date: Optional[date] = None
    abstract_deadline: Optional[date] = None
    full_paper_deadline: Optional[date] = None
    camera_ready_deadline: Optional[date] = None
    venue: Optional[str] = None
    year: int
    relevance_score: int = Field(ge=0, le=10)
    relevance_reason: str

class AgentState(BaseModel):
    thesis_keywords: list[str]
    thesis_abstract_summary: str
    found_conferences: list[Conference] = []
    seen_acronyms: set[str] = set()
    iteration: int = 0
    queries_tried: list[str] = []

class AgentRunResult(BaseModel):
    conferences_added: int
    conferences_skipped_dedup: int
    total_candidates_evaluated: int
    iterations_used: int
    estimated_cost_usd: float
    top_conferences: list[Conference]
