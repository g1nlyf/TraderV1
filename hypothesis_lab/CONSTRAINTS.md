# CONSTRAINTS — Locked Facts for Every Session

## Evaluation Standard (NON-NEGOTIABLE)
Every hypothesis MUST pass this gate to be considered valid:
1. **Temporal holdout** — train strictly on past data, test strictly on future data
2. **Purge + embargo** — drop samples straddling train/test boundary (label horizon bleed)
3. **Triple-barrier labels** — label each entry by which barrier hits first: profit-take / stop / time
4. **Permutation null** — compare rule-selected subset vs 20,000 random same-size subsets
5. **Block-bootstrap CI95** — confidence interval must not span zero for PASS verdict
6. **OOS only counts** — train metrics are informational, test metrics are the verdict

Bypass any of these = result is UNTRUSTED. Do not promote.

## Promotion Gate
- **Minimum EV/trade to consider**: > +1.0% net (after costs)
- **Minimum win rate improvement**: > +3pp over base
- **Minimum n**: > 100 OOS events
- **Champion replacement threshold**: new strategy must beat current champion by > 0.5% net EV OOS

## Known Anti-Patterns (Proven Failures — Do Not Retry)
- **Token-disjoint split**: leaks market regime (train+test in same window). Always use TEMPORAL split.
- **LLM as entry signal generator**: models v2–v6 were in-sample-leaky or noise-fit. Failed OOS every time.
- **Composite-scoring formula imitation**: formula net-EV = -0.0119 (negative). Training on it clones the loss.
- **Cross-sectional momentum on liquid majors (H-12)**: TEST Sharpe -1.05, perm_p 0.91. Dead.
- **Cross-sectional reversion on liquid majors (H-10)**: TEST Sharpe -2.39. Dead.
- **LP farming (H-16)**: neutral net always negative (IL > fees). Dead unless specific pool selection.
- **Hold-with-stop on memecoins (H-17)**: mean +142% but median -0.94%, skew +24.8 — lottery, not edge.
- **Win-rate-implied EV as a metric (H-001)**: computing EV as `wr*0.20 − (1−wr)*0.12 − cost`
  assumes every trade hits a hard barrier. Most exit by time with small payoffs. This metric
  manufactured the C-001 "champion" (+1.57% implied vs −0.97% realized). ALWAYS use realized
  mean payoff via `finetune/pipeline/eval_stats.py`. Higher win-rate ≠ positive EV.
- **Mean-reversion drawdown entry on memecoins (C-001/H-001)**: realized OOS EV −0.97%,
  edge over base −0.80%, perm_p 0.887, negative in every temporal slice. Anti-selective
  (fires on names whose losers slam the stop). Dead. Do not rebuild with regime filters.

## Data Assets Available
| Asset | Source | Coverage | Notes |
|-------|--------|---------|-------|
| Solana memecoin OHLCV | GeckoTerminal | 332 tokens, ~57 days | In DB: token_ohlcv |
| Binance spot hourly | Binance API | 115 pairs, ~730 days | In finetune/data/ |
| Binance perp funding | Binance + Bybit | 44-46 assets, 2,190 periods | In finetune/data/funding_cache/ |
| Helius on-chain txns | Helius RPC | Active collection | forward_collector_state.jsonl |
| Wallet metrics | WalletScarper DB | ~7 wallets | wallet_metric_snapshots |
| Token outcomes | WalletScarper DB | ~9 tokens | wallet_token_outcomes |

## Cost Model
- Memecoin entry/exit: 1.8% round-trip (slippage + fee)
- Binance spot: 5.5 bps/side taker, 1.0 bps/side maker
- Binance perp: same as spot
- Break-even: must beat costs before calling it "edge"

## Critical Infrastructure
- Champion config: `finetune/inference/entry_champion.json`
- Backtesting harness: `finetune/pipeline/backtest_harness.py`
- Mean-reversion strategy: `finetune/pipeline/meanrev_strategy.py`
- Funding signal: `finetune/pipeline/funding_signal.py`
- Walk-forward log: `finetune/data/meanrev_log.jsonl`
- Majors strategy: `finetune/pipeline/majors_meanrev.py`

## Environment Variables
All API keys live in `WalletScarper/.env`. Copy to session environment:
```powershell
# Load env vars before running any script
Get-Content WalletScarper/.env | Where-Object { $_ -match "^[A-Z_]+=.+" } | ForEach-Object {
    $parts = $_ -split "=", 2; [System.Environment]::SetEnvironmentVariable($parts[0], $parts[1], "Process")
}
```

Key vars: HELIUS_API_KEY, OPENROUTER_API_KEY, ANTHROPIC_API_KEY (if set)

## LLM Role (Correct Usage)
- GOOD: hypothesis generation, meta-reasoning, regime classification, result synthesis
- GOOD: fine-tuned models as RESIDUAL layer on top of deterministic rule (not replacement)
- BAD: LLM as primary entry signal (proven leaky/noise-fit OOS every time tried)

## Target
- Current champion: **NONE.** C-001 invalidated 2026-06-04 (H-001): realized EV −0.97%,
  perm_p 0.887. The "+1.57%" was a win-rate-implied artifact. Stack is empty.
- Target: +5.0%+ stable net EV/trade (REALIZED), validated multi-regime walk-forward.
- Intermediate gate: +2.0% realized net EV/trade, perm_p<0.05, CI95>0, n>100 to promote.
