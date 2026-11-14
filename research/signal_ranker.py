"""Offline, paper-only ML experiment. No broker or order submission dependency."""
from dataclasses import dataclass
from math import fsum, isfinite, sqrt
from statistics import mean
from typing import Iterable

FEATURES = ("trigger_strength", "relative_volume", "volatility_bps", "spread_bps")
STRATEGY = "equity-breakout-v1"


@dataclass(frozen=True)
class Candidate:
    signal_id: str
    strategy: str
    observed_at: int
    expires_at: int
    features: tuple[float, ...]
    # Supplied by the deterministic gate service, never by the model.
    blocked_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class Example:
    candidate: Candidate
    label_at: int
    gross_bps: float
    cost_bps: float

    @property
    def net_bps(self) -> float:
        return self.gross_bps - self.cost_bps


@dataclass(frozen=True)
class Model:
    version: str
    trained_through: int
    centers: tuple[float, ...]
    scales: tuple[float, ...]
    weights: tuple[float, ...]
    intercept: float

    def score(self, candidate: Candidate) -> float:
        return self.intercept + fsum(
            weight * ((value - center) / scale)
            for value, center, scale, weight in zip(
                candidate.features, self.centers, self.scales, self.weights, strict=True
            )
        )


def eligible(c: Candidate, now: int, max_age: int) -> bool:
    return (
        c.strategy == STRATEGY and not c.blocked_reasons
        and 0 <= now - c.observed_at <= max_age and now < c.expires_at
        and len(c.features) == len(FEATURES) and all(isfinite(v) for v in c.features)
        and all(v >= 0 for v in c.features)
    )


def split(examples: Iterable[Example], holdout_start: int) -> tuple[list[Example], list[Example]]:
    """Drop training labels crossing the holdout boundary, including equal timestamps."""
    train, holdout = [], []
    for row in examples:
        if (not eligible(row.candidate, row.candidate.observed_at, 0)
            or row.label_at <= row.candidate.observed_at
            or not isfinite(row.net_bps) or not isfinite(row.cost_bps) or row.cost_bps < 0):
            raise ValueError("Invalid qualified example or label")
        if row.candidate.observed_at >= holdout_start:
            holdout.append(row)
        elif row.label_at < holdout_start:
            train.append(row)
    return train, holdout


def fit(rows: list[Example], version: str) -> Model:
    if len(rows) < 8 or not version:
        raise ValueError("Prototype requires eight examples and a model version")
    columns = list(zip(*(r.candidate.features for r in rows), strict=True))
    centers = tuple(mean(col) for col in columns)
    scales = tuple(sqrt(mean((x - mu) ** 2 for x in col)) or 1.
                   for col, mu in zip(columns, centers, strict=True))
    matrix = [tuple((v - mu) / sd for v, mu, sd in zip(r.candidate.features, centers, scales, strict=True))
              for r in rows]
    intercept = mean(r.net_bps for r in rows)
    y = [r.net_bps - intercept for r in rows]
    weights = [0.] * len(FEATURES)
    # Ridge regression with fixed settings. Features and target are centered on training rows only.
    for _ in range(240):
        residual = [fsum(a * b for a, b in zip(x, weights, strict=True)) - label
                    for x, label in zip(matrix, y, strict=True)]
        weights = [w - .08 * (mean(x[i] * err for x, err in zip(matrix, residual, strict=True)) + .1 * w)
                   for i, w in enumerate(weights)]
    if not all(isfinite(w) for w in weights):
        raise ValueError("Nonfinite fitted weights")
    return Model(version, max(r.label_at for r in rows), centers, scales, tuple(weights), intercept)


def shadow_rank(candidates: Iterable[Candidate], now: int, model: Model | None, max_age: int = 30) -> dict:
    """Return baseline and shadow lists; neither list grants execution permission."""
    rows = sorted((c for c in candidates if eligible(c, now, max_age)),
                  key=lambda c: (-c.features[0], c.features[3], -c.observed_at, c.signal_id))
    baseline = [c.signal_id for c in rows]
    result = {"baseline": baseline, "shadow": [], "model": None, "mode": "paper-shadow"}
    if model is None or not rows or any(c.observed_at <= model.trained_through for c in rows):
        return result
    scores = [(c.signal_id, model.score(c)) for c in rows]
    if all(isfinite(s) for _, s in scores):
        result["shadow"] = [i for i, _ in sorted(scores, key=lambda x: -x[1])]
        result["model"] = model.version
    return result


def evaluate(train: list[Example], holdout: list[Example], version: str) -> dict:
    if not holdout or not train or max(r.label_at for r in train) >= min(r.candidate.observed_at for r in holdout):
        raise ValueError("Holdout must follow all training labels")
    model = fit(train, version)
    groups: dict[int, list[Example]] = {}
    for row in holdout:
        groups.setdefault(row.candidate.observed_at, []).append(row)
    outcomes = []
    for now, rows in sorted(groups.items()):
        rank = shadow_rank((r.candidate for r in rows), now, model)
        labels = {r.candidate.signal_id: r.net_bps for r in rows}
        if len(labels) != len(rows) or not rank["baseline"] or not rank["shadow"]:
            raise ValueError("Invalid or unavailable holdout comparison")
        outcomes.append((labels[rank["baseline"][0]], labels[rank["shadow"][0]]))
    return {"windows": len(outcomes), "train_examples": len(train), "holdout_examples": len(holdout),
            "baseline_mean_net_bps": mean(a for a, _ in outcomes),
            "shadow_mean_net_bps": mean(b for _, b in outcomes),
            "promotion": "not_evaluated"}


def demo() -> dict:
    # Intentionally invented labels: demonstrates mechanics, never market evidence.
    rows = [Example(Candidate(f"{t}-{i}", STRATEGY, t, t + 30,
                              (1. + i, 1. + ((t // 60 + i * 2) % 5), 15. + i, 2. + i)),
                    t + 20, 4. * (1. + ((t // 60 + i * 2) % 5)), 2. + i)
            for t in range(60, 2400, 60) for i in range(3)]
    train, holdout = split(rows, 1800)
    return {"data": "synthetic_example_only", **evaluate(train, holdout, "demo-ridge-v1")}


if __name__ == "__main__":
    import json
    print(json.dumps(demo(), indent=2))
