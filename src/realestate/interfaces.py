from __future__ import annotations

from typing import Protocol, runtime_checkable

from realestate.models import Property, Score, ScoredProperty


@runtime_checkable
class PropertySource(Protocol):
    name: str

    def fetch(self, **filters) -> list[Property]: ...


@runtime_checkable
class Scorer(Protocol):
    name: str
    weight: float

    def score(self, prop: Property, context: list[Property]) -> Score: ...


@runtime_checkable
class OutputFormatter(Protocol):
    name: str

    def format(self, results: list[ScoredProperty], dest: str | None = None) -> None: ...
