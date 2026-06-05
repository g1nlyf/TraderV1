# H-119 — H-042 magnitude sharpener: only enter when cascade is >10% AND within first 4h

**Status:** proposed · 2026-06-05
**Zone:** MICROSTRUCTURE SIGNALS — cascade magnitude + timing filter
**ID range:** H-119 (Zone 3 generation)

## Statement
H-042 at −8% H2 gives +1.46%/trade (t 2.24, n=91). The limiting constraint is n<100.
This idea adds two sharpening filters to improve the signal:
1. **Magnitude filter:** only −10%+ intraperiod drops (H-042 showed −10% H2 gives +2.36%/trade
   but n=36). Raise n by lowering the 8h threshold while adding INTRAPERIOD timing.
2. **First-half filter (H-042 tag H1 vs H2):** H-042 tests H1 (first 8h after cascade) and H2
   (second 8h). H2 (+1.46%) outperforms H1. This hypothesis adds a 1m intraperiod filter:
   cascade must happen in the first 4h of the 8h period (so the recovery window is symmetric);
   cascades in the last 4h don't have the same intraperiod recovery opportunity.

Combined: the set of cascade events with drop >8%, occurring in the first 4h of the funding
period, held for 2 periods — is predicted to show higher EV and better significance.

## Structural logic
**Structural:** Cascades in the last 2h before an 8h close have the market moving into a funding
settlement — the price may not recover before the close, reducing the H-042 signal. Cascades
in the first 4h have the most time for liquidation-desk recycling and mean-reversion.

## Falsifier
First-half cascade filter does NOT improve H-042 EV; or n is too small to test (< 50 events
after filtering); or the timing within the funding period has no effect.

## Data status
**HAVE** — 1m perp data for 10 names (180d) in `finetune/data/intraday_1m/`. Can identify exact
timestamp of the intraperiod cascade touch and classify first/second half.

## Test (one line)
New script on `finetune/data/intraday_1m/`: for each 8h period, find the first 1m bar with
cumulative return < −8% from period open; flag as "first-half" if it occurs in minutes 0–240
vs "second-half" (240–480); compare H-042 EV and n for each subgroup; permutation test.

## SCORE: 7.5
(edge_plausibility=4, data_feasibility=5, novelty=3 → (4×2+5+3)/4 = 4.0 → 8.0; capped at 7.5
due to small n=10 names and further subsetting may drop n below threshold)
