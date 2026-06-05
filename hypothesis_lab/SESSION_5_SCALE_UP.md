# SCALE-UP DIRECTIVE — paste into current running chat

---

New directive. Scale up. Everything below supersedes the 20-idea loop from the session prompt.

## Architecture: 100 generate → 50 survive filter → parallel test by data group

### Phase G: Generate 100 hypotheses using taxonomy

Dispatch **5 parallel generator agents**, each covering one taxonomy zone (20 ideas each).
Each agent: read INDEX.md + CONSTRAINTS.md dead-track list, generate 20 ideas from its zone,
score each (edge_plausibility×2 + feasibility + novelty) / 4, write ALL ≥6.5 as full H-XXX.md
files (not 7.0 — be generous at generation, ruthless at test). Assign IDs sequentially from
current max+1. Write one-line summary + score to hypothesis_lab/hypotheses/INDEX.md.

**Zone 1 (Forced-flow premia — Agent 1):**
Anything where the counterparty is FORCED and cannot adapt: liquidation cascades (variants of H-042),
margin-call clusters, forced unwinds at specific price levels, stop-loss hunting patterns, OI
concentration breaks, funding-clamp events, forced deleveraging after extreme vol spikes, cascade
spillover (A liquidates → B follows), post-circuit-breaker reopening dynamics, short-squeeze
unwinds, forced rebalancing by leveraged ETFs, whale position exits that move price, forced arb
unwinds when basis blows out, crowded-trade unwinds measured by funding change rate, forced longs
exiting on funding spikes, liquidation depth (how many contracts cleared), repeat-cascade events.

**Zone 2 (Carry and premia extensions — Agent 2):**
Beyond the 10-name book: funding carry on non-Binance/Bybit venues (OKX, Bybit exotic pairs),
cross-margin vs isolated funding differential, high-funding names filtered by recent OI trend,
funding seasonality at month-end (derivatives expiry), carry on perpetuals vs quarterly futures
basis, multi-exchange funding convergence as entry timing, funding during high-volatility regimes
(is it more or less capturable?), basis compression timing, funding in low-liquidity windows,
new exchange listings with funding anomalies, funding after major protocol upgrades, stablecoin
funding carry (USDC/USDT perps), cross-collateral carry stacking.

**Zone 3 (Microstructure signals — Agent 3):**
Bid-ask spread spikes as informed-trading proxy, order-book imbalance at key levels,
large-trade direction persistence (do whale trades predict short-term direction?), maker/taker
ratio as sentiment signal, funding rate vs open interest divergence (one rises, other flat),
perp premium vs spot as crowding signal, mid-price impact after large fills, realized vol
regime switching (low vol → enter; high vol → exit carry), spread compression after cascade
as carry quality filter, tick-level momentum on 1m data, volume-weighted funding vs time-weighted,
latency arbitrage between venues (predictable from data), OI-adjusted carry (normalize by leverage),
implied vol from perp spread, spread-to-funding ratio as entry quality.

**Zone 4 (Calendar/event-driven — Agent 4):**
Options/futures expiry → gamma-related flow (end of month), Federal Reserve meeting days (macro
vol spike → funding spike → carry entry), CPI/NFP data releases effect on crypto funding,
Bitcoin halving proximity carry (crowded long bets), quarterly perp expiry vs perpetual basis,
day-of-week funding patterns (weekend leverage unwind), time-to-funding-settlement carry premium
(enter 1h before, exit after), major protocol unlock schedule effects, exchange maintenance windows
(reduced liquidity → spread widens → carry premium), bitcoin ETF flow days (identified from on-chain
or news), year-end tax-loss carry effects on funding, token vesting schedule carry.

**Zone 5 (Cross-asset, macro, on-chain — Agent 5):**
BTC realized vol as carry on/off gate (high vol → higher funding but riskier), ETH gas price
as DeFi activity proxy → funding demand, DeFi TVL changes and perp funding correlation,
SOL on-chain transaction volume vs perp demand, stablecoin flows (USDT mint/burn) as macro
sentiment, BTC dominance as alt-carry predictor, cross-exchange BTC funding divergence as
arb signal, macro risk-on/off regime (SPX direction) vs crypto funding levels, crypto fear/greed
index (when extreme) as carry sizing input, Solana forward-collector wallet signals (H-040),
liquidation heatmap as entry timing, futures basis vs treasury yield spread (is crypto carry
competing with TradFi?).

---

### Phase F: Filter 100 → 50

**One filter agent reads ALL generated H-XXX files and scores them:**
- Hard kills: requires data not in cache and not fetchable in <30min (kill)
- Hard kills: re-tests a dead track (kill)
- Rank survivors by: (edge_plausibility × 2 + data_feasibility + novelty) / 4
- Output: ranked shortlist of top 50, written to hypothesis_lab/sessions/[today]-filter-50.md
- Update INDEX.md status to "queued-top50" or "filtered-out" for each

---

### Phase T: Test 50 in parallel — grouped by data dependency

**Critical architecture: collect each data type ONCE, project all hypotheses onto it.**

**Step T1 — Data collection (parallel, one script per data type):**

```python
# Collect ALL data groups simultaneously (background scripts):
# DataGroup A: Binance perp 8h funding + OI + volume — full 730d, 50+ names
# DataGroup B: 1m perp+spot for 10 carry names (already in intraday_1m/)
# DataGroup C: WalletScarper DB state (wallet_token_outcomes, forward_collector n)
# DataGroup D: Binance spot 1h for 50 liquid pairs (majors + alts)
# Write each group to finetune/data/[group_name]_collected_[date].pkl
```

Run all data collection scripts simultaneously. Continue to T2 while they run.

**Step T2 — Dispatch test agents grouped by data dependency:**

Group A hypotheses (need funding panel only — already in cache, no wait):
→ Dispatch **3 agents in parallel**, each testing 8-10 A-group hypotheses.
Each agent: load the shared funding panel ONCE, loop through its hypotheses, test each,
write results. Score through eval_stats. Report EV/perm_p/CI95/n for each.

Group B hypotheses (need 1m intraday data):
→ Wait for intraday_1m to confirm complete (it is — 20 files).
→ Dispatch **2 agents in parallel**, each testing 5-8 B-group hypotheses.

Group C hypotheses (need Solana/wallet data):
→ Check forward_collector n. If n≥30 tokens with outcomes: dispatch 1 agent.
→ If n<30: document as "forward-collect-pending" in INDEX.md, skip for now.

Group D hypotheses (need spot OHLCV):
→ After DataGroup D collected: dispatch **2 agents**, each testing 8-10 D-group.

**Step T3 — Rating and ranking all 50 results:**

One synthesis agent reads all H-XXX.md files from the tested batch. Computes:
- **Score = EV_net / max(CI_half_width, 0.001) × sign(EV_net)** (EV normalized by uncertainty)
- Adjusted for n: multiply by min(n/100, 2.0) (penalize low-n, cap at 2×)
- Flag gate candidates: EV>2% AND perm_p<0.05 AND CI95>0 AND n>100
- Rank all 50 from best to worst
- Write ranking to hypothesis_lab/sessions/[today]-ranking-50.md
- Update INDEX.md with all verdicts
- **IMMEDIATELY PROMOTE** any gate-clearer to champion status (create C-XXX file)

---

### Phase L: Loop

After ranking:
1. Top 10 failures → write "gap analysis" (what would have to be true for this to work?)
2. Gap analysis feeds next generation cycle (generate 100 more, this time more targeted)
3. Go to Phase G

**Loop continues until:**
- New champion promoted (beyond C-002)
- Or explicit stop

**Heartbeat every test-agent completion:**
`[HH:MM] Group [X] done — N tests, M passed gate, champion APR now Y%. Next: [what's running]`

---

### One more thing: parallel ≠ sequential within an agent

When an agent has 10 hypotheses to test against the same dataset, it should run them as a BATCH
(one data load, loop through tests) rather than one test per agent. The agents parallelize
between data groups, not within them. This is the right tradeoff: minimal data loading overhead,
maximum hypothesis throughput.

Go. Generate 100. Test 50. Find the next champion.
