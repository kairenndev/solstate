# solstate

**An auto-updating report on the state of the Solana ecosystem** — network health,
validator decentralisation, and economics — rendered as an interactive dashboard,
a readable Markdown report, and machine-readable JSON.

**[→ Live dashboard](https://kairenndev.github.io/solstate/)** · updated hourly by GitHub Actions

No API keys. No dependencies. Python standard library only.

```bash
git clone https://github.com/kairenndev/solstate
cd solstate
python -m solstate
# writes out/index.html, out/report.md, out/report.json
```

That is the entire setup. There is no `pip install` step because there is nothing
to install, and no `.env` because there is nothing to authenticate.

---

## Why it is built this way

**No keys, no dependencies.** Every source used here — Solana RPC, DeFiLlama,
CoinGecko — is reachable without registration. A report that needs five API keys
is a report nobody else can run, and a dependency list is a list of things that
can break between you writing it and someone else running it.

**The repository is the database.** Each run appends one line to
`history/snapshots.jsonl` and commits it. That file is the baseline the anomaly
detector compares against. No database, no hosting, no state outside git —
and the history is auditable in the commit log.

**Failures are reported, not hidden.** Individual collectors degrade
independently: if CoinGecko is down, the network section still renders. But every
swallowed failure is gathered and printed in all three outputs. Silent
degradation is how a dashboard ends up confidently displaying stale nonsense.

---

## What it measures

### Network
Non-vote TPS, total TPS, real slot time, epoch progress with time remaining,
block height, circulating supply.

**Vote transactions are separated from the rest.** They are consensus overhead
and they are the majority of traffic. Reporting a combined figure produces an
impressive number that means very little, so both are shown.

### Validators
Active and delinquent counts, delinquent share *of stake*, total stake,
top validators, and the **Nakamoto coefficient** — how many of the largest
validators together control one third of stake, the threshold at which the chain
can be halted.

The brief asked for stake distribution. A stake table is data that still needs
interpreting; the Nakamoto coefficient is the interpretation. One number answers
"how fragile is this network" directly.

Delinquency is reported by stake as well as by count for the same reason: a
hundred small delinquent validators is noise, one large one is a signal.

### Economy
SOL price and market cap, TVL **with its rank among all chains**, DEX volume and
venue concentration, network fees, stablecoin supply by peg.

TVL is ranked because absolute TVL moves with the whole market — it falls when
everything falls, which says nothing about Solana specifically. Rank shows
movement relative to competitors.

**Fees are reported as fees.** The brief asks for Real Economic Value. REV has no
single agreed methodology, so labelling a fee total "REV" would quietly
substitute one measure for another. What is measured is fees; readers can apply
their own REV definition on top.

---

## Anomaly detection

Two detectors, because either alone has a blind spot.

**Absolute thresholds** catch conditions that are bad regardless of history:
unhealthy RPC nodes, slot time above 600 ms, delinquent stake above 1% (warning)
or 5% (critical), Nakamoto coefficient below 15. Statistics alone would miss the
first occurrence of something catastrophic.

**Robust statistical deviation** catches conditions that are only meaningful
relative to normal: a $2.4B DEX day is unremarkable on its own and alarming if
the last month averaged $6B. Thresholds alone would miss regime changes.

The statistical detector uses **median and MAD, not mean and standard
deviation**. A single spike drags a mean far enough to hide the next spike —
precisely the failure mode an anomaly detector cannot afford. Deviation is scaled
by 0.6745 so the threshold reads as a familiar z-score; the cutoff is 3.5.

It stays silent until at least 8 snapshots exist. Below that, "normal" would be
invented rather than observed, and the report would cry wolf on its first runs.

---

## Automation

`.github/workflows/update.yml` runs hourly, regenerates all three outputs into
`docs/`, appends to history, and commits. GitHub Pages serves `docs/` as the live
dashboard.

Hourly is a considered interval: the slowest upstream sources refresh a few times
a day, the fastest metric is a 5-minute rolling average, and a daily cadence
would make anomaly detection pointless — a chain incident is long over before the
next daily snapshot.

To run it on your own schedule, change the `cron` line. To run it somewhere other
than GitHub, any scheduler that can execute `python -m solstate --out docs` works;
nothing in the project depends on Actions.

---

## Output formats

| File | For |
|---|---|
| `docs/index.html` | Interactive dashboard: sortable tables, hover readouts on sparklines, dark theme. Fully self-contained — no CDN, no fonts, no network calls at view time. Opens from disk. |
| `docs/report.md` | Readable as rendered Markdown and as plain text. The format people paste into Discord, Notion, or an issue. |
| `docs/report.json` | Structured, stable keys, every metric including the ones the other two summarise. |
| `history/snapshots.jsonl` | One flattened snapshot per run. The anomaly baseline. |

---

## Options

```
python -m solstate                 # write into out/
python -m solstate --out docs      # write somewhere else
python -m solstate --no-history    # dry run: do not append a snapshot
```

Exit code is 0 even when individual sources fail. A partial report is still
useful, and a non-zero exit would make a scheduled job look broken when it is in
fact doing its job.

---

## Layout

```
solstate/
  rpc.py         JSON-RPC client with endpoint failover
  http.py        stdlib HTTP with backoff, honours Retry-After
  network.py     TPS, slot time, epoch, supply, validators
  economy.py     price, TVL, DEX volume, fees, stablecoins
  history.py     append-only snapshot log
  anomalies.py   threshold + robust statistical detection
  markdown.py    Markdown rendering
  dashboard.py   self-contained HTML dashboard
  __main__.py    collect → detect → render
```

Solana's public RPC returns 429 under any real load, so `rpc.py` rotates across
three endpoints with backoff. Without that, the report would break exactly when
someone tries to read it.

---

## Sources

- Solana JSON-RPC — `getRecentPerformanceSamples`, `getEpochInfo`, `getSupply`,
  `getVoteAccounts`, `getHealth`
- DeFiLlama — TVL by chain, DEX volume, fees, stablecoin supply
- CoinGecko — SOL price, market cap, 24h change

## Licence

MIT.
