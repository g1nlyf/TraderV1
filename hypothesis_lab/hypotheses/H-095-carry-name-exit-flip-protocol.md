# H-095 — Name-level exit protocol: drop names on funding sign-flip (C-002 Rule 3 operationalized)

**Status:** proposed · 2026-06-05
**Zone:** Carry & Premia Extensions
**ID range:** H-095 (Zone 2 gen)
**SCORE:** 7.25  (edge_plausibility 7, data_feasibility 9, novelty 7) / 4 = 7.25

## Statement
C-002 Risk Rule 3 states: "if a held name's funding turns persistently negative, drop it." Operationalize this as a testable rule: if a name's EWMA funding (span=12 periods, ~4 days) crosses below zero, drop it from the book and replace with the next-best name by training-set level. Hypothesis: this dynamic name maintenance prevents the book from holding names whose structural long imbalance has reversed, without reintroducing the H-13 dynamic-chasing failure mode.

## Who is forced / why can't stop
When a name's EWMA funding crosses negative, the forced-payer dynamic has inverted: shorts are now paying longs. Staying in the carry position with negative funding is a guaranteed loser. The replacement rule (next-best by train level) is conservative — it avoids chasing the current top-K (H-13 trap) by using pre-committed train rankings.

## Falsifier
If the book with the exit protocol has WORSE OOS Sharpe than the always-held fixed book (C-002 baseline), name exits hurt through unnecessary turnover. Also falsified if the exit events are too rare (< 5 distinct exits in 657 OOS periods) to distinguish from random.

## Why uncaptured
C-002 lists this as a qualitative operating rule but it has never been backtested. The distinction from H-13 dynamic chasing is critical: H-13 re-ranked names every period by current funding level. This rule only acts on SIGN FLIP events using pre-committed replacement rankings — it is a reactive exit, not proactive chasing.

## Data status
data_status: HAVE
- Funding panel 8h 730d — EWMA and sign-flip detection trivially computable

## Test (one line)
Extend `carry_leads.py`: track EWMA-12 funding per name; when EWMA crosses below zero for any book name, swap it for the top train-ranked non-book name; compute OOS carry series; compare Sharpe/APR/turnover vs static C-002 baseline via `fh.evaluate`.
