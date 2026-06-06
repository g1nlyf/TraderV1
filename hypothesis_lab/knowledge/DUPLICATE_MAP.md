# DUPLICATE MAP — collapsing redundant H-IDs

> Sprint 4 ran 5 independent zone-agents that converged on the same ideas with different IDs.
> 114 hypothesis files exist; INDEX documents H-001..H-079 individually and collapses H-080..H-159
> into 2 batch rows. This map records concept-level duplicates so we stop double-counting.
> **Rule going forward: one concept = one canonical ID; variants are sub-notes, not new IDs.**

## Confirmed concept-duplicate clusters (H-080..H-159 batch)

| Concept | Canonical | Duplicate IDs (same idea) | Verdict (all) |
|---------|-----------|---------------------------|---------------|
| Carry ⊕ H-042 uncorrelated stack | **H-099** | H-110, H-149 | within CI of C-002; stack not CI-separated (sleeve n=39) |
| BTC realized-vol regime gate on carry | **H-080** | H-092, H-100, H-116, H-140, H-146, H-158 | gated ≈ always-on; eff-n≈18 regime shapes → no edge |
| BTC trend / return regime filter | **H-141** | H-147 | within CI |
| Funding dispersion / skew sizing | **H-082** | H-090, H-143, H-159 | within CI |
| Basis-compression timing | **H-087** | H-101, H-117, H-125 | within CI |
| Selection composite (level × persistence / quality) | **H-089** | H-115 (AR1), H-145 (low-beta) tested as variants | within CI of H-021 base |
| BTC-vol → leverage scalar (de-risker) | **H-091** | H-150, H-142 (H-042 sizing variant) | risk rule, not edge; maxDD≈flat |
| 1m intraperiod entry sharpening | **H-103** | H-109, H-130 | needs 1m tick; partially blocked |
| Settlement/calendar funding premium | **H-124** | H-123, H-125, H-133, H-139 | low-n; H-043 already refuted seasonality |

## Macro/calendar batch (H-120..H-139) — all BLOCKED or low-n
H-120 FOMC-eve, H-121 FOMC-day, H-122 CPI/NFP, H-126 halving, H-127 post-FOMC, H-128 pre-CPI,
H-129 expiry, H-131 FOMC-spread-beta, H-134 NFP, H-135 halving-quartile, H-136 ETF-flow, H-137 unlock,
H-138 post-CPI. **No macro/event calendar cached → all BLOCKED.** Do not treat as tested.

## Cross-listing/blocked sleeves
H-096 (OKX), H-097 (quarterly basis), H-098 (USDC-margin), H-102/H-113 (OI), H-111/H-112 (L2),
H-118 (options), H-153 (SPX), H-154 (stablecoin flow), H-155 (DeFi TVL), H-156 (gas/activity). All
data-BLOCKED — see DEAD_TRACKS §blocked.

## Action taken
- INDEX.md keeps the 2 batch rows but now points here for the per-ID resolution.
- No files deleted (audit trail preserved). Future hypotheses: check this map before assigning an ID;
  if the concept exists, extend the canonical note instead of minting H-160+.
