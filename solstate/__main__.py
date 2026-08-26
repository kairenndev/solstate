"""Entry point: collect, detect, render.

    python -m solstate                 # write all three formats into out/
    python -m solstate --out public    # somewhere else
    python -m solstate --no-history    # do not append a snapshot (dry run)

Exit code is 0 even when individual sources fail. A partially collected report
is still useful, and a non-zero exit would make the scheduled job look broken
when it is in fact doing its job. Only a total failure to write output is fatal.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import anomalies, dashboard, economy, history, markdown, network

SOURCES = [
    "Solana JSON-RPC (api.mainnet-beta.solana.com and public fallbacks)",
    "DeFiLlama — TVL, DEX volume, fees, stablecoin supply",
    "CoinGecko — SOL price and market cap",
]


def _collect_errors(node, path=""):
    """Walk the report and surface every `error` a collector recorded.

    Individual collectors degrade quietly so one dead source cannot take the
    report down. That is the right behaviour, but silent degradation is how a
    dashboard ends up confidently showing stale nonsense, so every swallowed
    failure is gathered here and printed in the output.
    """
    found = []
    if isinstance(node, dict):
        if "error" in node and isinstance(node["error"], str):
            found.append(f"{path or 'report'}: {node['error']}")
        for key, value in node.items():
            if key != "error":
                found.extend(_collect_errors(value, f"{path}.{key}" if path else key))
    return found


def build(out_dir: Path, *, record: bool = True) -> dict:
    started = time.monotonic()

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "network": network.collect(),
        "economy": economy.collect(),
        "sources": SOURCES,
    }
    report["collection_seconds"] = round(time.monotonic() - started, 1)
    report["errors"] = _collect_errors({k: v for k, v in report.items() if k != "sources"})

    past = history.append(report) if record else history.load()
    report["anomalies"] = anomalies.detect(report, past)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "report.md").write_text(markdown.render(report), encoding="utf-8")
    (out_dir / "index.html").write_text(dashboard.render(report, past), encoding="utf-8")

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="solstate", description=__doc__)
    parser.add_argument("--out", default="out", help="output directory (default: out)")
    parser.add_argument("--no-history", action="store_true",
                        help="do not append a snapshot to history")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    report = build(out_dir, record=not args.no_history)

    found = report["anomalies"]["count"]
    errors = len(report["errors"])
    print(
        f"solstate: wrote {out_dir}/index.html, report.md, report.json "
        f"in {report['collection_seconds']}s "
        f"({found} anomal{'y' if found == 1 else 'ies'}, {errors} collection error(s))"
    )
    for finding in report["anomalies"]["findings"]:
        print(f"  [{finding['severity']}] {finding['metric']}: {finding['message']}")
    for error in report["errors"]:
        print(f"  [source] {error}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
