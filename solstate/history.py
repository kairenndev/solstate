"""Append-only snapshot history.

Anomaly detection needs a baseline, and a baseline needs memory. Every run
appends one compact line to history/snapshots.jsonl; the CI workflow commits it
back to the repository, so the baseline grows on its own with no database and
no hosting. The file is the state.

JSONL rather than JSON: appending a line is atomic enough for our purposes and
never rewrites what is already there, so a crashed run cannot corrupt history.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HISTORY_FILE = Path("history/snapshots.jsonl")

# Roughly a month of hourly runs. Enough for weekly seasonality to show up,
# small enough that the file stays readable and the repository stays light.
MAX_SNAPSHOTS = 750


def _flatten(report: dict[str, Any]) -> dict[str, Any]:
    """Reduce a full report to the handful of scalars worth tracking over time.

    Storing whole reports would balloon the file and bury the signal. These are
    the series an anomaly is actually visible in.
    """
    net = report.get("network", {})
    eco = report.get("economy", {})

    def dig(*path, default=None):
        node: Any = report
        for key in path:
            if not isinstance(node, dict):
                return default
            node = node.get(key)
        return node if isinstance(node, (int, float)) else default

    return {
        "ts": report.get("generated_at"),
        "tps_non_vote": dig("network", "performance", "tps_non_vote"),
        "tps_total": dig("network", "performance", "tps_total"),
        "slot_time_ms": dig("network", "performance", "slot_time_ms"),
        "delinquent_stake_pct": dig("network", "validators", "delinquent_stake_pct"),
        "nakamoto": dig("network", "validators", "nakamoto_coefficient"),
        "sol_usd": dig("economy", "price", "usd"),
        "tvl_usd": dig("economy", "tvl", "tvl_usd"),
        "dex_volume_24h_usd": dig("economy", "dex_volume", "volume_24h_usd"),
        "fees_24h_usd": dig("economy", "fees", "fees_24h_usd"),
        "stablecoins_usd": dig("economy", "stablecoins", "total_usd"),
        # Kept for context when reading raw history by hand.
        "epoch": (net.get("epoch") or {}).get("epoch") if isinstance(net.get("epoch"), dict) else None,
        "healthy": bool((net.get("health") or {}).get("ok")) if isinstance(net.get("health"), dict) else None,
    }


def load(path: Path = HISTORY_FILE) -> list[dict[str, Any]]:
    """Read history, skipping any line that got truncated mid-write."""
    if not path.exists():
        return []

    snapshots = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            snapshots.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a partial trailing line must not break the whole run
    return snapshots


def append(report: dict[str, Any], path: Path = HISTORY_FILE) -> list[dict[str, Any]]:
    """Append the current snapshot and return the full history including it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = _flatten(report)
    snapshot.setdefault("ts", datetime.now(timezone.utc).isoformat())

    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, separators=(",", ":")) + "\n")

    history = load(path)

    # Trim from the front when the file outgrows the window. Rewriting here is
    # safe: it happens once every few hundred runs, not on the hot path.
    if len(history) > MAX_SNAPSHOTS:
        history = history[-MAX_SNAPSHOTS:]
        path.write_text(
            "\n".join(json.dumps(s, separators=(",", ":")) for s in history) + "\n",
            encoding="utf-8",
        )

    return history
