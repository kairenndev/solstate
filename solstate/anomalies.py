"""Anomaly detection over the snapshot history.

Two detectors, deliberately:

1. Absolute thresholds — for conditions that are bad regardless of history.
   A 30% delinquent stake is an emergency whether or not it happened before.
2. Statistical deviation (robust z-score) — for conditions that are only
   meaningful relative to normal. A $2.4B DEX day is unremarkable on its own
   and alarming if the last month averaged $6B.

Thresholds alone miss regime changes; statistics alone miss the first
occurrence of something catastrophic. Both are cheap, so both are here.

Median and MAD rather than mean and standard deviation: a single spike drags a
mean far enough to hide the next spike, which is precisely the failure mode an
anomaly detector cannot afford.
"""

from __future__ import annotations

from typing import Any, Iterable

# Minimum history before statistical detection is trusted. Below this a "normal"
# range is invented rather than observed, and the report would cry wolf on its
# first few runs.
MIN_HISTORY = 8

# 0.6745 converts MAD into a standard-deviation-equivalent scale, so the
# threshold below reads like a familiar z-score.
MAD_TO_SIGMA = 0.6745
Z_THRESHOLD = 3.5

SERIES_LABELS = {
    "tps_non_vote": ("Non-vote TPS", "tx/s"),
    "slot_time_ms": ("Slot time", "ms"),
    "sol_usd": ("SOL price", "USD"),
    "tvl_usd": ("TVL", "USD"),
    "dex_volume_24h_usd": ("DEX volume 24h", "USD"),
    "fees_24h_usd": ("Network fees 24h", "USD"),
    "stablecoins_usd": ("Stablecoin supply", "USD"),
    "delinquent_stake_pct": ("Delinquent stake", "%"),
}


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _numeric(history: Iterable[dict[str, Any]], key: str) -> list[float]:
    return [s[key] for s in history if isinstance(s.get(key), (int, float))]


def _threshold_checks(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Conditions that are bad on their own terms, no history required."""
    found: list[dict[str, Any]] = []
    net = report.get("network", {})
    perf = net.get("performance") or {}
    vals = net.get("validators") or {}
    health = net.get("health") or {}

    if health.get("ok") is False:
        found.append({
            "severity": "critical",
            "metric": "node health",
            "message": "RPC nodes did not report a healthy status.",
        })

    slot_ms = perf.get("slot_time_ms")
    if isinstance(slot_ms, (int, float)) and slot_ms > 600:
        found.append({
            "severity": "warning",
            "metric": "slot time",
            "message": f"Slot time {slot_ms} ms is well above the 400 ms target; the chain is running slow.",
        })

    delinquent = vals.get("delinquent_stake_pct")
    if isinstance(delinquent, (int, float)):
        if delinquent > 5:
            found.append({
                "severity": "critical",
                "metric": "delinquent stake",
                "message": f"{delinquent}% of stake is delinquent. Above ~33% the chain halts.",
            })
        elif delinquent > 1:
            found.append({
                "severity": "warning",
                "metric": "delinquent stake",
                "message": f"{delinquent}% of stake is delinquent, above the usual sub-1% background.",
            })

    nakamoto = vals.get("nakamoto_coefficient")
    if isinstance(nakamoto, int) and nakamoto < 15:
        found.append({
            "severity": "warning",
            "metric": "nakamoto coefficient",
            "message": f"Only {nakamoto} validators together control a third of stake — enough to halt the chain.",
        })

    return found


def _statistical_checks(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deviation of the latest value from its own recent normal."""
    if len(history) < MIN_HISTORY:
        return []

    found: list[dict[str, Any]] = []
    latest = history[-1]
    baseline = history[:-1]

    for key, (label, unit) in SERIES_LABELS.items():
        current = latest.get(key)
        series = _numeric(baseline, key)
        if not isinstance(current, (int, float)) or len(series) < MIN_HISTORY - 1:
            continue

        median = _median(series)
        mad = _median([abs(v - median) for v in series])
        if mad == 0:
            continue  # a perfectly flat series has no meaningful deviation

        z = MAD_TO_SIGMA * (current - median) / mad
        if abs(z) < Z_THRESHOLD:
            continue

        direction = "above" if z > 0 else "below"
        change = (current - median) / median * 100 if median else 0
        found.append({
            "severity": "warning",
            "metric": label,
            "message": (
                f"{label} is {abs(round(change, 1))}% {direction} its recent median "
                f"({current:,.4g} vs {median:,.4g} {unit}); z={round(z, 1)}."
            ),
        })

    return found


def detect(report: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    """Run both detectors and return findings plus enough context to trust them."""
    findings = _threshold_checks(report) + _statistical_checks(history)
    order = {"critical": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: order.get(f["severity"], 3))

    return {
        "count": len(findings),
        "critical": sum(1 for f in findings if f["severity"] == "critical"),
        "baseline_snapshots": max(len(history) - 1, 0),
        "statistical_detection_active": len(history) >= MIN_HISTORY,
        "findings": findings,
    }
