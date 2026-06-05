# H-116 — BTC realized-vol regime as alt-carry timing gate

**Status:** proposed · 2026-06-05
**Zone:** MICROSTRUCTURE SIGNALS — BTC vol regime as systemic gate
**ID range:** H-116 (Zone 3 generation)

## Statement
BTC's 8h realized vol is the systemic risk proxy for the entire crypto market. When BTC vol
is elevated (top-quartile rolling 20-period), the correlation between alt liquidation cascades
and BTC drops; the carry book's funding rates are less stable; the H-042 events are more severe
but also harder to isolate as per-name vs. beta. Gate BOTH C-002 (carry) and H-042 (cascade
bounce) on BTC vol regime: full size in low-BTC-vol; half size in medium; zero in high.

## Structural logic
**Who is forced / structural:** In high-BTC-vol regimes, forced liquidations are systematic
(correlated across names) — they are BTC-beta events, not per-name overshoots. Market-neutral
strategies (both carry and H-042) lose their neutrality when the whole market moves together.
Gating on BTC vol preserves the market-neutrality assumption.

## Falsifier
BTC vol regime has no predictive power for C-002 or H-042 per-period returns; or high-BTC-vol
periods show HIGHER per-name excess (the stress creates MORE opportunity, not less).

## Why uncaptured
BTC data is in the existing panel (`funding_leads2.py` uses `p["btc"]`). Using it as a vol
gate (rather than a correlation measure, which H-036 showed is near zero on average) is a
novel use of the existing BTC data.

## Data status
**HAVE** — BTC 8h closes for 730d in the existing funding panel. Realized-vol = rolling std
of 8h BTC returns. Fully computable from `p["btc"]` in `funding_leads2.py`.

## Test (one line)
Extend `funding_leads2.py`: compute rolling 20-period BTC return std; regime-gate carry and
H-042 evaluation to low-BTC-vol periods; compare gated vs always-on APR/Sharpe.

## SCORE: 7.5
(edge_plausibility=4, data_feasibility=5, novelty=3 → (4×2+5+3)/4 = 4.0 → 8.0; slight reduction
to 7.5 because H-036 already showed BTC beta≈0 for the book on average — the regime-gating
angle is different but may have similar null result)

## Results (2026-06-05) — `test_carry_cluster.py` — NOT CI-separated (no flag)
As anticipated by the H-036 null, the BTC realized-vol timing gate does not separate. Rolling-21
BTC-vol percentile gate on the C-002 book: best (p60, 0.5× above) APR +1.39% · Sh 3.84 vs always-on
+1.49% / 3.54 — Sharpe lift within CI, APR lower, eff-n≈18 autocorrelated ON-runs. The falsifier
("high-BTC-vol shows higher excess") is not what drives it; the gate simply trims variance without a
separable reward. **Verdict: gate-candidate N.**
