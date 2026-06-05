---
type: research
date: 2026-06-04
tags:
  - research
  - trader
  - experiments-ledger
ai-first: true
status: tested
---
## For future Claude
This is the core register of the [[index|TraderV1 experiment ledger]]. Each entry states a hypothesis, the data and method used to measure it, the parameters swept, and the numbers obtained. Entries contain measurements only — no verdicts, no "worked/did not work." Notation: `EV` = mean return per event/trade; `Sharpe` = annualized unless noted; `perm_p` = permutation-null p-value; `CI95` = 95% block-bootstrap interval; `n` = sample count; `bps` = basis points; `OOT` = out-of-time 70/30 split (parameters chosen on the first 70% of the timeline, metrics reported on the last 30%). See [[methods]] for procedure definitions, [[datasets]] for data, [[tools]] for engines.

# Hypotheses Register

## H-03 — Drawdown-threshold entry rule (re-measured under permutation null)
- **Statement.** Entry rule: `drawdown_from_high < −0.10 AND range_pct > median AND buy_pressure_6 > median`; payoff via triple-barrier (+20% / −12%, cost 1.8%).
- **Data.** Holdout file `holdout_mom3_eval.jsonl`, n=1360 labeled bars.
- **Method.** Apply fixed thresholds; compute rule win-rate vs base win-rate; permutation null = mean outcome of the rule-selected subset vs 20,000 random same-size subsets.
- **Measurements.** base_win 0.382; rule_win 0.406 (Δ +2.4pp); fired 224; perm_p 0.2298. Triple-barrier EV: base −1.565%, rule −0.800%.
- **Status.** tested · 2026-06-04.

## H-10 — Cross-sectional reversion (dollar-neutral)
- **Statement.** Per rebalance, weight ∝ −(trailing k-bar return − cross-sectional mean); long/short, gross 1, dollar-neutral.
- **Data.** Binance spot hourly, 44 USDT pairs, ~730 days, 17,520 bars.
- **Method.** OOT 70/30; metrics net of fee; permutation null (shuffle forward returns across assets within each rebalance); BTC 7-day-trend regime split; fee sweep.
- **Parameters.** look ∈ {1,2,3,6,12,24}h; hold ∈ {1,2,3,6,12,24}h; construction ∈ {continuous, decile}; fee 5.0 bps/side.
- **Measurements.** Best train config (continuous, look24h, hold24h) train Sharpe −0.87. TEST mean −0.256%/rebal, Sharpe −2.39, hit 47.0%, maxDD −51.2%, n=219. CI95 [−0.508%, −0.057%]. perm_p 0.998. Regime: BTC-up −0.218%, BTC-down −0.287%. No fee in the 0–30 bps sweep produced a positive test mean.
- **Status.** tested · 2026-06-04.

## H-11 — Time-series oversold-bounce, index-hedged
- **Statement.** Per asset, signal = drawdown from rolling-`look` high; long when drawdown < threshold; hedge by shorting the equal-weight index (payoff = asset forward return − index forward return).
- **Data.** Binance spot hourly; run 1 = 44 pairs; run 2 = 115 pairs (top by 24h volume), ~730 days.
- **Method.** Grid select on train per-trade t-statistic; report test EV/win; per-trade net (asset round-trip 2×fee); BTC regime split; permutation = oversold set vs random same-size set.
- **Parameters.** look ∈ {24,48,72,168}h; dd ∈ {−5,−10,−20}%; hold ∈ {6,12,24}h; volatility filter on/off; fee 5.5 bps/side.
- **Measurements.**
  - Run 1 (44 assets), selected dd<−20% look72h hold24h vol=on: train t +2.62; TEST gross EV +0.43%, net +0.33%, win 51.4%, n=72; CI95 [−1.30%, +2.16%]; selection p 0.07; breakeven 21.6 bps; regime BTC-up +0.18% / down −0.05%.
  - Run 2 (115 assets, same locked config): TEST gross −0.68%, net −0.78%, win 42.7%, n=560; CI95 [−1.41%, −0.14%]; selection p 1.00; regime BTC-up −0.78% / down −0.65%.
- **Status.** tested · 2026-06-04.

## H-12 — Cross-sectional momentum (dollar-neutral, daily/weekly)
- **Statement.** Per rebalance, weight ∝ +(trailing return − cross-sectional mean); long/short, dollar-neutral.
- **Data.** Binance spot hourly, 115 pairs, ~730 days.
- **Method.** OOT 70/30; permutation null; regime split; fee sweep. Same engine as H-10 with sign reversed.
- **Parameters.** look ∈ {24,72,168,336,720}h (1–30d); hold ∈ {24,72,168}h; continuous/decile; fee 5.0 bps/side.
- **Measurements.** Best train config (decile, look720h, hold72h) train Sharpe +1.86, train mean +0.283%/rebal, hit 57.7%, n=163. TEST mean −0.182%/rebal, Sharpe −1.05, hit 52.9%, maxDD −11.3%, n=70. CI95 [−0.449%, +0.258%]. perm_p 0.910. Regime: BTC-up −0.201%, BTC-down −0.167%.
- **Status.** tested · 2026-06-04.

## H-13 — Perpetual funding carry (delta-neutral)
- **Statement.** Hold a delta-neutral book that receives funding; side chosen at t−1 from sign(EWMA of past funding); net = Σ funding·side − fee·side-changes (+ price leg in the basis-aware variant).
- **Data.** Binance + Bybit 8h funding history, ~730 days, 2,190 periods; 46 assets on Binance, 40 with Bybit. Basis-aware variant adds Binance spot+perp 8h closes.
- **Method.** EWMA span selected on train; OOT 70/30; block-bootstrap CI; BTC regime split; fee sweep + breakeven; "tradeable" filter = real spot + ≥90% history coverage.
- **Parameters.** EWMA span ∈ {1,3,6,12,24}; fee taker 5.5 bps/leg and maker 1.0 bps/leg; top-K = 10.
- **Measurements (annualized return, APR).**
  - Descriptive: mean funding +2.4% APR, median +3.6% APR, lag-1 funding-sign persistence 72.6%.
  - Single-venue all-names, taker: train +3.0% (Sharpe 11.7), TEST −0.2% (Sharpe −0.9), CI95 [−1.1%, +0.9%], breakeven 5.5 bps.
  - Single-venue all-names, maker: TEST +2.9% (Sharpe 14.5), CI95 [+2.2%, +3.8%], regime +3.9%/+2.3%.
  - Top-10, maker: TEST +9.0% (Sharpe 11.3), hit 80.7%, maxDD −0.2%, CI95 [+6.1%, +12.5%], regime +11.6%/+7.4%; breakeven 4.5 bps. Taker: TEST −3.2%.
  - Cross-venue spread (Binance−Bybit), taker: TEST −8.7% (Sharpe −27.0), CI95 [−10.0%, −7.6%], breakeven 1.5 bps.
  - Basis-aware (funding + spot_ret − perp_ret), maker: all-names TEST +3.1% (Sharpe 8.08), CI95 [+2.2%, +4.0%], regime +3.8%/+2.7%; top-10 TEST +9.4% (Sharpe 8.97), CI95 [+6.3%, +12.9%], regime +11.4%/+8.2%.
  - Tradeable universe (24 names, basis-aware, maker): all-names TEST +0.7% (Sharpe 2.14), CI95 [+0.2%, +1.1%], regime +0.8%/+0.7%; top-10 TEST +0.1% (Sharpe −0.05).
  - Mid-liquidity-alt subset (24 names): all-names TEST +0.7% (Sharpe 1.45).
  - Per-name standalone carry (maker, full window): 44/45 names positive, median +4.1% APR; top-1 share 10%, top-3 share 24% of total positive carry; highest-carry names included tokenized-equity/commodity perps (e.g. NVDA, MSTR, XAG, XAU) and recently-listed tokens.
  - **Capturability re-measurement (2026-06-04, scripts/h013_tradeable_carry.py, 50 names, 730d, maker 1bp).** single_topk FULL universe TEST apr +9.1% Sharpe 11.39 — but RESTRICTED to the 29-name tradeable universe (real Binance spot leg + ≥90% history) single_topk TEST apr −0.1% (Sharpe −0.06). The +9.1% requires per-period selection of spot-less/illiquid perps (H, LAB, CRCL, MSTR) on which long-spot/short-perp is not executable. Diversified tradeable single (EW, basis-aware, maker) TEST apr +0.8% Sharpe 1.79 CI95 [+0.2%,+1.3%]. Cross-venue (Binance−Bybit) spread re-tested at MAKER 1bp: TEST apr +0.6% Sharpe 3.93 hit 54.9% CI95 [+0.0%,+1.1%] breakeven 1.5bps (vs taker apr −9.6%).
- **Status.** tested · 2026-06-04. Capturability re-measured 2026-06-04 (tradeable filter + xvenue maker).

## H-14 — Funding as a directional positioning signal
- **Statement.** (a) cross-sectional: long low-funding-z / short high-funding-z (reversal) or the reverse (momentum); pnl = neutral portfolio of forward perp returns. (b) event study: per (asset,t) with |funding z|>threshold, market-hedged forward perp return.
- **Data.** Cached Binance funding (8h) + perp 8h closes, 44 assets, 2,190 periods.
- **Method.** Rolling z-score (no-lookahead); OOT 70/30; permutation null; BTC regime split; event study with block-bootstrap CI; fee taker 5.5 bps.
- **Parameters.** z-window ∈ {30,90}; hold ∈ {1,3,9} periods; event thresholds {1.5, 2.0}.
- **Measurements.**
  - Cross-sectional reversal (z90, hold9p): train Sharpe +1.50; TEST APR +8.6%, Sharpe +0.30, hit 49.3%, n=73; mean +0.0707%/rebal; CI95 [−0.543%, +0.341%]; perm_p 0.309; regime up −0.04% / down +0.15%.
  - Cross-sectional momentum (z30, hold3p): TEST APR −46.4%, Sharpe −1.43, n=219; perm_p 0.729.
  - Event study (n 1,410–2,563 across grid): EV/event range −0.188% to +0.025%; win 41.6%–44.0%; t-stat −1.39 to +0.10; CI95 spans zero at every (threshold,hold).
- **Status.** tested · 2026-06-04.

## H-15 — Drawdown entry on memecoins, SOL-hedged
- **Statement.** Per token, long when drawdown from rolling high < threshold; outcome = forward return; hedged variant subtracts SOL forward return.
- **Data.** GeckoTerminal hourly OHLCV, 13 tokens, ~57 days; SOL hourly from Binance.
- **Method.** Per-event payoffs; OOT split by time; round-trip cost 1.5%; permutation = oversold events vs random events; SOL 7-day-trend regime split; engine selftest confirms hedge zeroes pure-beta tokens.
- **Parameters.** look ∈ {6,12,24}h; dd ∈ {−10,−20,−30}%; hold ∈ {6,12,24}h. Selected look24h dd<−10% hold24h.
- **Measurements.**
  - Unhedged: TEST EV/event +16.04%, win 49.7%, t +7.31, n=1559; perm_p 0.666; regime SOL-up −5.67% / down +18.06%.
  - Neutral (long token − short SOL): TEST EV/event +17.59%, win 52.2%, t +7.99; perm_p 0.666; regime SOL-up −4.55% / down +19.65%.
  - **Overlap re-measurement (2026-06-04, scripts/h015_resolve.py).** TEST window spans 13d; 1559 events over 321 distinct entry-hours (4.9× overlap). Cluster-robust t on per-bucket mean payoffs: 6h-bucket eff n=54 t=+4.12; 1d eff n=14 t=+3.02; 3d eff n=6 t=+1.93; 7d eff n=2 t=+1.14. Permutation null at 20k iters perm_p=0.679. SOL-down events 1426/1559 (91%).
- **Status.** tested · 2026-06-04. Re-measured 2026-06-04 (overlap/effective-n).

## H-16 — LP fee income vs impermanent loss
- **Statement.** Constant-product full-range LP. Per window, fee income = fee_rate·Σvolume/reserve; IL = (1+k)/2 − √k (k = price ratio); unhedged net = (√k − 1) + fees − gas; neutral net = fees − IL − gas.
- **Data.** GeckoTerminal OHLCV+volume + current reserve, 12 pools, 8,682 pool-hours. Survivorship-corrected IL distribution computed on WalletScarper `token_ohlcv` (24 tokens ≥120h, 1,228 windows).
- **Method.** Windowed; OOT; block-bootstrap CI; SOL regime split; gas/fee sweep. Engine selftest confirms IL formula, crash case, gas monotonicity. Pool-selection: per-pool train/test split, rank by train neutral net.
- **Parameters.** hold ∈ {24,72,168}h; fee ≈ 0.25%; gas $2 (sweep $0.5–$10), LP capital $1000.
- **Measurements.**
  - Fee income/window: +0.78% (24h), +1.97% (72h), +3.45% (168h). IL/window: 1.54%, 3.95%, 6.51%.
  - Neutral net/window: −0.95% (24h), −2.18% (72h), −3.25% (168h); CI95 below zero; both SOL regimes negative.
  - Unhedged net/window: −3.48%, −8.72%, −10.92%.
  - Pool-selection (hold72h, n=14): corr(train net, test net) +0.73; train-net>0 pools (4) → test mean +1.52% (4/4 positive); train-net≤0 pools (10) → test mean −2.86%.
  - Survivorship IL (72h): median 0.22%, mean 43.78%, p90 8.80%; price ratio k median 1.00, mean 2.19; share of windows with k>2 = 9.4%.
- **Status.** tested · 2026-06-04.

## H-17 — Hold-with-stop on token sample
- **Statement.** Buy each token at uniform entry points; hold horizon, exit at horizon or when price ≤ entry·stop (fill at the bar's close on breach); return net of cost.
- **Data.** WalletScarper `token_ohlcv`, 332 tokens (≥24 bars), step 12h, horizon 72h.
- **Method.** Per-entry returns; aggregate mean/median/win/skew; cost 2%.
- **Parameters.** stop ∈ {none, −50%, −30%}.
- **Measurements (n=1515).** no-stop: mean +142.51%, median −0.94%, win 48.6%, p95 +241%, skew +24.8. stop −50%: mean +141.41%. stop −30%: mean +130.14%, median −1.82%, win 45.3%.
- **Status.** tested · 2026-06-04.

## H-18 — Early-buyer reconstruction and forward collection
- **Statement.** For each token, reconstruct early buyers near launch from chain; features (distinct buyers, overlap with tracked/scored wallets, early buy-SOL, concentration); outcome = forward return; test feature vs forward return under permutation null.
- **Data.** Helius RPC + Enhanced Transactions; WalletScarper DB (`token_ohlcv` 332 tokens for outcomes; `wallet_token_outcomes` for tracked wallets; `wallet_metric_snapshots` for win-rate). GeckoTerminal `new_pools`/`trending_pools` for forward discovery.
- **Method.** Reconstruction path: paginate pool signatures toward the early window, Enhanced-parse, trader = feePayer, decode buys, join to OHLCV forward return. Forward path: snapshot new launches' early buyers from chain page-1, update outcomes after horizon, permutation-null test at n≥30.
- **Parameters.** window 1h; horizon 24h; page budget 20 (reconstruction); snapshot max age 6h (forward).
- **Measurements.**
  - Reconstruction smoke (4 outcome tokens): early buyers 0 for all; `reached_start` False; observed forward-24h values among the 4: +14.7%, +34.1%, +129.1%, +8030.2%.
  - Forward collector first tick: discovered 60 pools, snapshotted 19 launches; early buyers per token 0–47; early buy-SOL 0–108.2; overlap with tracked/scored wallet sets 0.
  - Joinability of existing DB: `wallet_token_outcomes` 1,422 rows over 13 real tokens, 1,330 wallets, `roi_bucket` populated 1/1422; `token_ohlcv` 332 tokens; intersection of the two token sets 0; wallets with non-null win-rate 21 distinct.
- **Status.** tested · forward-collection running ([[tools|forward_collector]], hourly via Windows Task Scheduler `TraderV1_ForwardCollector`).
