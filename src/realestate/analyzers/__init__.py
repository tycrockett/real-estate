from __future__ import annotations

from realestate.models import Property, ScoredProperty

_registry: dict[str, type] = {}


def register(name: str):
    def decorator(cls):
        _registry[name] = cls
        return cls
    return decorator


def get_scorer(name: str, **kwargs):
    if name not in _registry:
        available = list(_registry.keys())
        raise KeyError(f"Unknown scorer '{name}'. Available: {available}")
    return _registry[name](**kwargs)


def available() -> list[str]:
    return list(_registry.keys())


def score_properties(
    properties: list[Property],
    scorers: list[tuple[str, float]] | None = None,
) -> list[ScoredProperty]:
    if not properties:
        return []

    if scorers is None:
        scorers = [(name, cls().weight) for name, cls in _registry.items()]

    active = [(get_scorer(name), weight) for name, weight in scorers]

    results = []
    for prop in properties:
        scores = []
        weighted_sum = 0.0
        total_weight = 0.0
        for scorer, weight in active:
            s = scorer.score(prop, properties)
            scores.append(s)
            weighted_sum += s.value * weight
            total_weight += weight
        total = round(weighted_sum / total_weight, 2) if total_weight > 0 else 0.0
        results.append(ScoredProperty(property=prop, scores=scores, total_score=total))

    results.sort(key=lambda r: r.total_score, reverse=True)
    return results


from realestate.analyzers import (  # noqa: E402, F401
    distress_stage,
    loan_age,
    equity_estimate,
    time_pressure,
    owner_occupied,
    price_per_sqft,
    cash_flow,
    comparative,
)
