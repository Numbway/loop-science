"""Schemas for standalone experiment report generation."""

from datetime import datetime

from pydantic import BaseModel


class ExperimentReportResponse(BaseModel):
    available: bool
    generated_at: datetime
    view_endpoint: str
    download_endpoint: str
