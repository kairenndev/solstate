"""Human-readable Markdown rendering of a report.

Markdown is the format people actually paste into Discord, Notion and GitHub
issues, so it is written to be readable as plain text too: no HTML fallbacks,
no wide tables that wrap into noise on a phone.
"""

from __future__ import annotations

from typing import Any

SEVERITY_MARK = {"critical": "🔴", "warning": "🟡", "info": "🔵"}


def _usd(value: Any, digits: int = 2) -> str:
    """Format money at the scale a reader thinks in, not in raw digits."""
    if not isinstance(value, (int, float)):
        return "n/a"
    for limit, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= limit:
            return f"${value / limit:,.{digits}f}{suffix}"
    return f"${value:,.{digits}f}"


def _num(value: Any, digits: int = 0) -> str:
    if not isinstance(value, (int, float)):
        return "n/a"
    return f"{value:,.{digits}f}"


def _pct(value: Any, digits: int = 2) -> str:
    if not isinstance(value, (int, float)):
        return "n/a"
    return f"{value:+.{digits}f}%"


def render(report: dict[str, Any]) -> str:
    net = report.get("network", {})
    eco = report.get("economy", {})
    anomalies = report.get("anomalies", {})

    perf = net.get("performance") or {}
    epoch = net.get("epoch") or {}
    supply = net.get("supply") or {}
    vals = net.get("validators") or {}
    price = eco.get("price") or {}
    tvl = eco.get("tvl") or {}
    dex = eco.get("dex_volume") or {}
    fees = eco.get("fees") or {}
    stables = eco.get("stablecoins") or {}

    lines: list[str] = [
        "# Solana Ecosystem State",
        "",
        f"*Generated {report.get('generated_at', 'n/a')} · "
        f"data collected in {report.get('collection_seconds', 0)}s*",
        "",
    ]

    # Anomalies go first: if something is wrong, that is the headline, not the
    # price. A report that buries the alert below the charts is a dashboard, not
    # a monitor.
    findings = anomalies.get("findings") or []
    if findings:
        lines += ["## ⚠ Anomalies", ""]
        for f in findings:
            mark = SEVERITY_MARK.get(f["severity"], "•")
            lines.append(f"- {mark} **{f['metric']}** — {f['message']}")
        lines.append("")
    else:
        note = (
            "Statistical detection is warming up; threshold checks are active."
            if not anomalies.get("statistical_detection_active")
            else f"Baseline: {anomalies.get('baseline_snapshots', 0)} snapshots."
        )
        lines += ["## Anomalies", "", f"None detected. {note}", ""]

    lines += [
        "## Network",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Non-vote TPS | {_num(perf.get('tps_non_vote'), 1)} |",
        f"| Total TPS (incl. votes) | {_num(perf.get('tps_total'), 1)} |",
        f"| Slot time | {_num(perf.get('slot_time_ms'), 1)} ms (target 400) |",
        f"| Epoch | {epoch.get('epoch', 'n/a')} — {_num(epoch.get('progress_pct'), 1)}% done, "
        f"~{_num(epoch.get('hours_remaining'), 1)}h left |",
        f"| Block height | {_num(epoch.get('block_height'))} |",
        f"| Circulating supply | {_num(supply.get('circulating_sol'))} SOL |",
        "",
        "## Validators",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Active | {_num(vals.get('active_count'))} |",
        f"| Delinquent | {_num(vals.get('delinquent_count'))} "
        f"({_num(vals.get('delinquent_stake_pct'), 3)}% of stake) |",
        f"| Total stake | {_num(vals.get('total_stake_sol'))} SOL |",
        f"| Nakamoto coefficient | **{vals.get('nakamoto_coefficient', 'n/a')}** |",
        "",
        "> The Nakamoto coefficient is how many of the largest validators together",
        "> control one third of stake — the threshold at which the chain can be",
        "> halted. Lower means more fragile.",
        "",
    ]

    top = vals.get("top_validators") or []
    if top:
        lines += [
            "<details><summary>Top 10 validators by stake</summary>",
            "",
            "| # | Identity | Stake (SOL) | Share | Commission |",
            "|---|---|---|---|---|",
        ]
        for i, v in enumerate(top, start=1):
            ident = v["identity"]
            short = f"{ident[:6]}…{ident[-4:]}"
            lines.append(
                f"| {i} | `{short}` | {_num(v['stake_sol'])} | {v['stake_pct']}% | {v['commission']}% |"
            )
        lines += ["", "</details>", ""]

    lines += [
        "## Economy",
        "",
        "| Metric | Value | 24h |",
        "|---|---|---|",
        f"| SOL price | {_usd(price.get('usd'))} | {_pct(price.get('change_24h_pct'))} |",
        f"| Market cap | {_usd(price.get('market_cap_usd'))} | |",
        f"| TVL | {_usd(tvl.get('tvl_usd'))} | rank #{tvl.get('rank', 'n/a')} of "
        f"{tvl.get('chains_total', 'n/a')} chains |",
        f"| DEX volume | {_usd(dex.get('volume_24h_usd'))} | {_pct(dex.get('change_24h_pct'))} |",
        f"| Network fees | {_usd(fees.get('fees_24h_usd'))} | {_pct(fees.get('change_24h_pct'))} |",
        f"| Stablecoin supply | {_usd(stables.get('total_usd'))} | |",
        "",
        "> Fees are reported as fees. The brief asks for Real Economic Value, but",
        "> REV has no single agreed methodology, so labelling a fee total as REV",
        "> would substitute one measure for another without saying so.",
        "",
    ]

    protocols = dex.get("top_protocols") or []
    if protocols:
        lines += ["**Top DEXs by 24h volume**", "", "| Venue | Volume | Share |", "|---|---|---|"]
        for p in protocols:
            lines.append(f"| {p['name']} | {_usd(p['volume_24h_usd'])} | {p['share_pct']}% |")
        lines.append("")

    sources = report.get("sources") or []
    if sources:
        lines += ["## Sources", ""] + [f"- {s}" for s in sources] + [""]

    errors = report.get("errors") or []
    if errors:
        lines += [
            "## Collection errors",
            "",
            "Listed rather than hidden: a metric missing for an unknown reason is",
            "worse than a metric missing for a stated one.",
            "",
        ] + [f"- `{e}`" for e in errors] + [""]

    lines += [
        "---",
        "",
        "Generated by [solstate](https://github.com/kairenndev/solstate) — "
        "Python standard library only, no API keys, no dependencies.",
    ]

    return "\n".join(lines)
