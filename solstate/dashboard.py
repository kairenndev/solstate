"""Self-contained interactive HTML dashboard.

Everything — styles, scripts, data, sparklines — is inlined into one file. No
CDN, no fonts, no XHR. Three reasons: it opens from disk with no server, it
cannot break because a third party went down, and GitHub Pages serves it as-is.

Dark theme, as the brief prefers.
"""

from __future__ import annotations

import html
import json
from typing import Any

# Chosen for contrast on a dark background rather than for brand: the point is
# that a red card is legible at a glance from across a desk.
CSS = """
:root {
  --bg: #0b0e14; --panel: #131822; --panel-2: #1a2130; --line: #232c3d;
  --text: #e6edf7; --dim: #8b98ad; --accent: #14f195; --accent-2: #9945ff;
  --warn: #ffb020; --crit: #ff4d5e; --ok: #14f195;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--text);
  font: 15px/1.55 ui-sans-serif, -apple-system, "Segoe UI", Roboto, sans-serif;
  padding: 32px 20px 64px;
}
.wrap { max-width: 1180px; margin: 0 auto; }
header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 12px; margin-bottom: 6px; }
h1 { font-size: 26px; margin: 0; letter-spacing: -.02em; }
h1 .dot { color: var(--accent); }
.meta { color: var(--dim); font-size: 13px; }
.meta code { color: var(--text); background: var(--panel-2); padding: 1px 6px; border-radius: 4px; }
h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .09em;
     color: var(--dim); margin: 34px 0 12px; font-weight: 600; }
.grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(215px, 1fr)); }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 12px;
        padding: 14px 16px; position: relative; overflow: hidden; }
.card .label { color: var(--dim); font-size: 12px; text-transform: uppercase; letter-spacing: .06em; }
.card .value { font-size: 25px; font-weight: 650; margin-top: 4px; letter-spacing: -.02em;
               font-variant-numeric: tabular-nums; }
.card .sub { color: var(--dim); font-size: 12.5px; margin-top: 2px; }
.up { color: var(--ok); } .down { color: var(--crit); }
.spark { margin-top: 8px; display: block; width: 100%; height: 30px; }
.alerts { margin: 20px 0 0; display: grid; gap: 8px; }
.alert { border-radius: 10px; padding: 11px 14px; font-size: 14px;
         border: 1px solid; display: flex; gap: 10px; align-items: flex-start; }
.alert.critical { background: rgba(255,77,94,.09); border-color: rgba(255,77,94,.42); }
.alert.warning  { background: rgba(255,176,32,.08); border-color: rgba(255,176,32,.36); }
.alert.clear    { background: rgba(20,241,149,.06); border-color: rgba(20,241,149,.28); color: var(--dim); }
.alert b { color: var(--text); }
table { width: 100%; border-collapse: collapse; font-size: 14px;
        background: var(--panel); border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }
th { text-align: left; color: var(--dim); font-weight: 600; font-size: 12px;
     text-transform: uppercase; letter-spacing: .06em; padding: 10px 14px;
     background: var(--panel-2); cursor: pointer; user-select: none; white-space: nowrap; }
th:hover { color: var(--text); }
th::after { content: " ⇅"; opacity: .3; }
th.asc::after { content: " ↑"; opacity: 1; color: var(--accent); }
th.desc::after { content: " ↓"; opacity: 1; color: var(--accent); }
td { padding: 9px 14px; border-top: 1px solid var(--line); font-variant-numeric: tabular-nums; }
tbody tr:hover { background: var(--panel-2); }
code.mono { font-family: ui-monospace, "Cascadia Code", Consolas, monospace; font-size: 12.5px; color: var(--dim); }
.bar { height: 4px; background: var(--panel-2); border-radius: 3px; overflow: hidden; margin-top: 8px; }
.bar > i { display: block; height: 100%; background: linear-gradient(90deg, var(--accent-2), var(--accent)); }
details { margin-top: 12px; background: var(--panel); border: 1px solid var(--line);
          border-radius: 12px; padding: 12px 16px; }
summary { cursor: pointer; color: var(--dim); font-size: 13px; }
summary:hover { color: var(--text); }
pre { overflow-x: auto; font-size: 12px; color: var(--dim); margin: 12px 0 0; }
footer { margin-top: 40px; color: var(--dim); font-size: 12.5px; border-top: 1px solid var(--line); padding-top: 16px; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.note { color: var(--dim); font-size: 12.5px; margin-top: 8px; }
"""

JS = """
// Sortable tables. Numeric columns are detected from a data-sort attribute so
// that "$1.2B" and "1200000000" sort by value, not by string.
document.querySelectorAll('table').forEach(function (table) {
  table.querySelectorAll('th').forEach(function (th, index) {
    th.addEventListener('click', function () {
      var body = table.tBodies[0];
      var rows = Array.prototype.slice.call(body.rows);
      var asc = !th.classList.contains('asc');
      table.querySelectorAll('th').forEach(function (o) { o.classList.remove('asc', 'desc'); });
      th.classList.add(asc ? 'asc' : 'desc');
      rows.sort(function (a, b) {
        var x = a.cells[index], y = b.cells[index];
        var xv = x.dataset.sort !== undefined ? parseFloat(x.dataset.sort) : NaN;
        var yv = y.dataset.sort !== undefined ? parseFloat(y.dataset.sort) : NaN;
        if (!isNaN(xv) && !isNaN(yv)) return asc ? xv - yv : yv - xv;
        return asc ? x.textContent.localeCompare(y.textContent)
                   : y.textContent.localeCompare(x.textContent);
      });
      rows.forEach(function (r) { body.appendChild(r); });
    });
  });
});

// Sparkline readout on hover: the shape shows the trend, the tooltip gives the
// number, so the chart stays uncluttered until asked.
document.querySelectorAll('svg.spark').forEach(function (svg) {
  var series = JSON.parse(svg.dataset.series || '[]');
  var card = svg.closest('.card');
  var sub = card && card.querySelector('.sub');
  var original = sub ? sub.textContent : '';
  if (!series.length || !sub) return;
  svg.addEventListener('mousemove', function (e) {
    var box = svg.getBoundingClientRect();
    var i = Math.min(series.length - 1,
                     Math.max(0, Math.round((e.clientX - box.left) / box.width * (series.length - 1))));
    sub.textContent = 'point ' + (i + 1) + '/' + series.length + ': ' + series[i].toLocaleString();
  });
  svg.addEventListener('mouseleave', function () { sub.textContent = original; });
});
"""


def _sparkline(series: list[float], *, width: int = 200, height: int = 30) -> str:
    """Inline SVG sparkline. Returns an empty string when there is nothing to
    draw — a flat line from two points is decoration pretending to be data."""
    values = [v for v in series if isinstance(v, (int, float))]
    if len(values) < 3:
        return ""

    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    step = width / (len(values) - 1)
    points = [
        f"{i * step:.1f},{height - 3 - (v - lo) / span * (height - 6):.1f}"
        for i, v in enumerate(values)
    ]
    rising = values[-1] >= values[0]
    colour = "var(--accent)" if rising else "var(--crit)"
    data = html.escape(json.dumps([round(v, 4) for v in values]), quote=True)

    return (
        f'<svg class="spark" viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
        f'data-series="{data}">'
        f'<polyline fill="none" stroke="{colour}" stroke-width="1.6" '
        f'stroke-linejoin="round" points="{" ".join(points)}"/>'
        f"</svg>"
    )


def _usd(value: Any, digits: int = 2) -> str:
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


def _change(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return ""
    cls = "up" if value >= 0 else "down"
    return f'<span class="{cls}">{value:+.2f}%</span>'


def _card(label: str, value: str, sub: str = "", spark: str = "") -> str:
    return (
        f'<div class="card"><div class="label">{html.escape(label)}</div>'
        f'<div class="value">{value}</div>'
        f'<div class="sub">{sub}</div>{spark}</div>'
    )


def render(report: dict[str, Any], history: list[dict[str, Any]]) -> str:
    net = report.get("network", {})
    eco = report.get("economy", {})
    anomalies = report.get("anomalies", {})

    perf = net.get("performance") or {}
    epoch = net.get("epoch") or {}
    vals = net.get("validators") or {}
    supply = net.get("supply") or {}
    price = eco.get("price") or {}
    tvl = eco.get("tvl") or {}
    dex = eco.get("dex_volume") or {}
    fees = eco.get("fees") or {}
    stables = eco.get("stablecoins") or {}

    def series(key: str) -> list[float]:
        return [s[key] for s in history if isinstance(s.get(key), (int, float))]

    # --- alerts -----------------------------------------------------------
    findings = anomalies.get("findings") or []
    if findings:
        alerts = "".join(
            f'<div class="alert {html.escape(f["severity"])}">'
            f'<b>{html.escape(f["metric"])}</b><span>{html.escape(f["message"])}</span></div>'
            for f in findings
        )
    else:
        detail = (
            f'baseline of {anomalies.get("baseline_snapshots", 0)} snapshots'
            if anomalies.get("statistical_detection_active")
            else "statistical detection still warming up; threshold checks active"
        )
        alerts = f'<div class="alert clear"><b>No anomalies</b><span>{html.escape(detail)}</span></div>'

    # --- network ----------------------------------------------------------
    progress = epoch.get("progress_pct") or 0
    network_cards = "".join([
        _card("Non-vote TPS", _num(perf.get("tps_non_vote"), 1),
              "excludes consensus votes", _sparkline(series("tps_non_vote"))),
        _card("Total TPS", _num(perf.get("tps_total"), 1),
              "including vote transactions", _sparkline(series("tps_total"))),
        _card("Slot time", f'{_num(perf.get("slot_time_ms"), 1)} <span class="sub">ms</span>',
              "target 400 ms", _sparkline(series("slot_time_ms"))),
        _card("Epoch", str(epoch.get("epoch", "n/a")),
              f'{_num(progress, 1)}% · ~{_num(epoch.get("hours_remaining"), 1)}h left'
              f'<div class="bar"><i style="width:{min(max(progress, 0), 100):.1f}%"></i></div>'),
        _card("Active validators", _num(vals.get("active_count")),
              f'{_num(vals.get("delinquent_count"))} delinquent '
              f'({_num(vals.get("delinquent_stake_pct"), 3)}% of stake)',
              _sparkline(series("delinquent_stake_pct"))),
        _card("Nakamoto coefficient", str(vals.get("nakamoto_coefficient", "n/a")),
              "validators controlling ⅓ of stake", _sparkline(series("nakamoto"))),
        _card("Circulating supply", f'{_num(supply.get("circulating_sol"))} <span class="sub">SOL</span>',
              f'{_num(supply.get("total_sol"))} total'),
    ])

    # --- economy ----------------------------------------------------------
    economy_cards = "".join([
        _card("SOL price", _usd(price.get("usd")),
              _change(price.get("change_24h_pct")) + " 24h", _sparkline(series("sol_usd"))),
        _card("Market cap", _usd(price.get("market_cap_usd")), "fully circulating"),
        _card("TVL", _usd(tvl.get("tvl_usd")),
              f'rank #{tvl.get("rank", "n/a")} of {tvl.get("chains_total", "n/a")} chains',
              _sparkline(series("tvl_usd"))),
        _card("DEX volume 24h", _usd(dex.get("volume_24h_usd")),
              _change(dex.get("change_24h_pct")) + f' · {_num(dex.get("protocols_count"))} venues',
              _sparkline(series("dex_volume_24h_usd"))),
        _card("Network fees 24h", _usd(fees.get("fees_24h_usd")),
              _change(fees.get("change_24h_pct")), _sparkline(series("fees_24h_usd"))),
        _card("Stablecoin supply", _usd(stables.get("total_usd")),
              "capital positioned to move", _sparkline(series("stablecoins_usd"))),
    ])

    # --- tables -----------------------------------------------------------
    validator_rows = "".join(
        f'<tr><td>{i}</td>'
        f'<td><code class="mono">{html.escape(v["identity"][:8])}…{html.escape(v["identity"][-6:])}</code></td>'
        f'<td data-sort="{v["stake_sol"]}">{_num(v["stake_sol"])}</td>'
        f'<td data-sort="{v["stake_pct"]}">{v["stake_pct"]}%</td>'
        f'<td data-sort="{v["commission"]}">{v["commission"]}%</td></tr>'
        for i, v in enumerate(vals.get("top_validators") or [], start=1)
    )
    dex_rows = "".join(
        f'<tr><td>{html.escape(str(p["name"]))}</td>'
        f'<td data-sort="{p["volume_24h_usd"]}">{_usd(p["volume_24h_usd"])}</td>'
        f'<td data-sort="{p["share_pct"] or 0}">{p["share_pct"]}%</td></tr>'
        for p in (dex.get("top_protocols") or [])
    )

    errors = report.get("errors") or []
    errors_block = ""
    if errors:
        items = "".join(f"<li><code class=\"mono\">{html.escape(str(e))}</code></li>" for e in errors)
        errors_block = (
            f"<details open><summary>Collection errors ({len(errors)})</summary>"
            f'<p class="note">Listed rather than hidden: a metric missing for an '
            f"unknown reason is worse than one missing for a stated reason.</p>"
            f"<ul>{items}</ul></details>"
        )

    raw = html.escape(json.dumps(report, indent=2, ensure_ascii=False))

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Solana Ecosystem State · solstate</title>
<style>{CSS}</style>
</head><body><div class="wrap">

<header>
  <h1>Solana Ecosystem State<span class="dot">.</span></h1>
  <span class="meta">generated <code>{html.escape(str(report.get('generated_at', 'n/a')))}</code>
  · collected in {report.get('collection_seconds', 0)}s
  · {len(history)} snapshots in history</span>
</header>

<div class="alerts">{alerts}</div>

<h2>Network</h2>
<div class="grid">{network_cards}</div>

<h2>Economy</h2>
<div class="grid">{economy_cards}</div>

<h2>Top validators by stake</h2>
<table><thead><tr><th>#</th><th>Identity</th><th>Stake (SOL)</th><th>Share</th><th>Commission</th></tr></thead>
<tbody>{validator_rows}</tbody></table>
<p class="note">The Nakamoto coefficient above counts how many of these together
reach one third of stake — the point at which the chain can be halted.</p>

<h2>Top DEXs by 24h volume</h2>
<table><thead><tr><th>Venue</th><th>Volume 24h</th><th>Share</th></tr></thead>
<tbody>{dex_rows}</tbody></table>

{errors_block}

<details><summary>Raw JSON</summary><pre>{raw}</pre></details>

<footer>
Built by <a href="https://github.com/kairenndev/solstate">solstate</a> ·
Python standard library only, no API keys, no dependencies ·
Sources: Solana RPC, DeFiLlama, CoinGecko ·
Fees are reported as fees, not relabelled as REV.
</footer>

</div><script>{JS}</script></body></html>"""
