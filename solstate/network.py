"""Solana network state: performance, epoch, supply, validator health.

Every collector returns a plain serialisable dict and never takes the whole
build down with it. If one source dies the report should ship with an honest
note about it rather than not ship at all.
"""

from __future__ import annotations

from typing import Any

from . import rpc

# Solana measures an epoch in slots. A slot is nominally 400 ms, but the real
# figure drifts, so time-to-epoch-end is estimated from the observed slot rate
# rather than from the nominal constant.
NOMINAL_SLOT_MS = 400
LAMPORTS_PER_SOL = 1_000_000_000


def _safe(fn, default=None):
    """Run a collector without letting one dead source kill the whole report."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - any network failure lands here
        return {"error": str(exc)} if default is None else default


def performance() -> dict[str, Any]:
    """Throughput and real slot duration from recent samples.

    `getRecentPerformanceSamples` returns 60-second windows. We average several:
    a single window is too noisy to say anything about network health.
    """
    samples = rpc.call("getRecentPerformanceSamples", [5]) or []
    if not samples:
        return {"error": "no performance samples returned"}

    total_tx = sum(s["numTransactions"] for s in samples)
    total_slots = sum(s["numSlots"] for s in samples)
    total_secs = sum(s["samplePeriodSecs"] for s in samples)

    # Vote transactions are consensus overhead, and they are the majority of
    # traffic. Reporting a combined figure yields an impressive number that
    # means very little. Both are exposed so the reader can tell them apart.
    non_vote = sum(s.get("numNonVoteTransactions") or 0 for s in samples)

    return {
        "tps_total": round(total_tx / total_secs, 1) if total_secs else None,
        "tps_non_vote": round(non_vote / total_secs, 1) if total_secs and non_vote else None,
        "slot_time_ms": round(total_secs * 1000 / total_slots, 1) if total_slots else None,
        "nominal_slot_time_ms": NOMINAL_SLOT_MS,
        "samples_used": len(samples),
        "window_secs": total_secs,
    }


def epoch() -> dict[str, Any]:
    """Current epoch progress and estimated time remaining."""
    info = rpc.call("getEpochInfo")
    slots_done = info["slotIndex"]
    slots_total = info["slotsInEpoch"]
    progress = slots_done / slots_total if slots_total else 0

    perf = performance()
    slot_ms = perf.get("slot_time_ms") or NOMINAL_SLOT_MS
    remaining_hours = (slots_total - slots_done) * slot_ms / 1000 / 3600

    return {
        "epoch": info["epoch"],
        "slot": info["absoluteSlot"],
        "block_height": info.get("blockHeight"),
        "slots_done": slots_done,
        "slots_in_epoch": slots_total,
        "progress_pct": round(progress * 100, 2),
        "hours_remaining": round(remaining_hours, 1),
    }


def supply() -> dict[str, Any]:
    """SOL supply. Circulating matters more than total: staking ratios are
    quoted against it."""
    data = rpc.call("getSupply", [{"excludeNonCirculatingAccountsList": True}])
    value = data["value"]
    return {
        "total_sol": round(value["total"] / LAMPORTS_PER_SOL),
        "circulating_sol": round(value["circulating"] / LAMPORTS_PER_SOL),
        "non_circulating_sol": round(value["nonCirculating"] / LAMPORTS_PER_SOL),
    }


def validators() -> dict[str, Any]:
    """Validator set composition and health.

    Delinquent validators have fallen behind consensus. Their share of stake is
    more informative than their count: a hundred small delinquent validators is
    noise, one large one is a signal.
    """
    data = rpc.call("getVoteAccounts")
    current = data["current"]
    delinquent = data["delinquent"]

    stake_current = sum(v["activatedStake"] for v in current)
    stake_delinquent = sum(v["activatedStake"] for v in delinquent)
    stake_total = stake_current + stake_delinquent

    ranked = sorted(current, key=lambda v: v["activatedStake"], reverse=True)

    # How many of the largest validators together control one third of stake.
    # One third is the halting threshold in Solana's consensus, which makes this
    # a direct measure of centralisation: the smaller the number, the more
    # fragile the network. Raw stake tables require interpretation; this does not.
    nakamoto, running = 0, 0
    for v in ranked:
        running += v["activatedStake"]
        nakamoto += 1
        if running > stake_total / 3:
            break

    return {
        "active_count": len(current),
        "delinquent_count": len(delinquent),
        "delinquent_stake_pct": round(stake_delinquent / stake_total * 100, 3) if stake_total else 0,
        "total_stake_sol": round(stake_total / LAMPORTS_PER_SOL),
        "nakamoto_coefficient": nakamoto,
        "top_validators": [
            {
                "identity": v["nodePubkey"],
                "stake_sol": round(v["activatedStake"] / LAMPORTS_PER_SOL),
                "stake_pct": round(v["activatedStake"] / stake_total * 100, 2) if stake_total else 0,
                "commission": v["commission"],
            }
            for v in ranked[:10]
        ],
    }


def health() -> dict[str, Any]:
    """Whether the node answers at all. Trivial, but without it an empty
    metric above is ambiguous: dead source or genuinely zero?"""
    try:
        result = rpc.call("getHealth")
        return {"ok": result == "ok", "raw": result}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "raw": str(exc)}


def collect() -> dict[str, Any]:
    """Collect the whole network section of the report."""
    return {
        "health": health(),
        "performance": _safe(performance),
        "epoch": _safe(epoch),
        "supply": _safe(supply),
        "validators": _safe(validators),
    }
