"""Pydantic models for the 6-bucket lesson prep sheet, mirroring
eduteach-simulation-host's PrepSheetRequest shape (see that repo's
app/main.py). Duplicated here rather than shared as a package, since the two
services are separately deployable -- this gives create_prep_sheet an
accurate, structured input schema for Claude/ChatGPT to fill in; the
simulation-host still does its own full validation on the way in.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PrepImage(BaseModel):
    url: str
    caption: str | None = None


class PrepWatchFor(BaseModel):
    text: str = Field(..., description="The likely misconception/mistake students will have.")
    fix: str = Field(..., description="One-line way to catch or correct it in the moment.")


class PrepSection(BaseModel):
    title: str
    minutes: int | None = None
    bullets: list[str] = Field(..., description="Short, concrete teaching steps for this section.")
    image: PrepImage | None = Field(None, description="One illustrative image for this section.")
    images: list[PrepImage] | None = Field(None, description="Several images for this section.")
    watch: PrepWatchFor | None = None


class PrepSheetRequest(BaseModel):
    """The 6-bucket lesson prep sheet: Refresher, Concept, Real Life,
    Challenge, Level Set, Explore. Omit `refresher` if no earlier lesson in
    this conversation needs recapping; omit `real_life` if there's no
    real-life tie-in for this topic. `concept`/`challenge`/`level_set`/
    `explore` are always expected."""

    topic: str
    goal: str | None = Field(None, description="One-line lesson objective.")
    floor: str | None = Field(None, description="The weakest-child fallback path/check.")
    refresher: PrepSection | None = None
    concept: PrepSection
    real_life: PrepSection | None = None
    challenge: PrepSection
    level_set: PrepSection
    explore: PrepSection
