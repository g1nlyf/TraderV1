# H-004 — Regime Filter: Disable Mean-Reversion in Trending Markets

**Status:** proposed
**Priority:** P0 (linked to H-001 fix)
**Asset universe:** Solana memecoins + SOL benchmark
**Created:** 2026-06-04

## Statement
The mean-reversion rule (H-champion) fails in trending regimes. Adding a regime gate that DISABLES the rule when SOL (or the memecoin universe index) is in a strong trend increases OOS win rate above 48% and prevents negative EV periods like 2026-06-01.

## Rationale ("million dollar idea")
Mean reversion works in range-bound markets. In trending markets, "buy the dip" is "catch the falling knife." Every quant fund filters strategies by regime — it's not optional. The existing rule fires indiscriminately. A 7-day SOL trend filter is a 2-line code change that could recover the edge immediately. If the degradation on June 1 was regime-driven, this is a free fix.

## Data required
- SOL hourly OHLCV from Binance (already available)
- Memecoin universe index (equal-weight of token_ohlcv tokens)
- `finetune/data/holdout_mom3_eval.jsonl` — existing holdout with regime tags

## Test method
1. Define regime: SOL 7d return > +threshold → "trending up", < -threshold → "trending down", else "ranging"
2. Re-run mean-reversion rule ONLY on bars where regime = "ranging"
3. Compare: rule win rate in ranging vs trending separately
4. OOS: temporal holdout on same dataset
5. If ranging-only win rate > 50% → PASS (regime filter adds value)

## Parameters
- SOL trend window: 3d, 5d, 7d, 14d
- Trend threshold: ±5%, ±10%, ±15%, ±20%
- Alternative regime signal: BTC 7d trend
- Alternative: memecoin universe volatility (VIX-analog)

## Results
```
[To be filled]
```

## Verdict
[ ] PASS  [ ] FAIL  [ ] INCONCLUSIVE

## Refinement path
**If regime filter works:**
→ Combine with Kelly sizing (H-005): bigger position in ranging regime, zero in trending
→ Add to champion: C-001 + H-004 = new champion

**If regime doesn't split the distribution:**
→ The degradation has a different cause → back to H-001 diagnosis
