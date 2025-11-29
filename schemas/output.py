from typing import List

from pydantic import BaseModel


class Plan(BaseModel):
    stages: List[dict]
    summary: str


class Output(BaseModel):
    plan: Plan
