# H-134 — NFP surprise direction × funding sign agreement

**Status:** proposed · 2026-06-05
**Zone:** CALENDAR / EVENT-DRIVEN
**Score:** 7.0
**Asset universe:** 29 tradeable Binance perps (funding 8h + spot price, 730d)
**Created:** 2026-06-05

## Statement
NFP "surprise" (actual minus consensus expectation, sign-coded as positive=risk-on or
negative=risk-off) can be HARDCODED from public BLS data + Bloomberg consensus 2024-2026.
When NFP surprise is risk-on (better-than-expected jobs) AND funding is ALREADY positive
(market positioned long), the post-NFP funding SPIKE is amplified (bulls-confirmed, more
longs piled in). When NFP surprise is risk-off AND funding is positive, forced longs get
stopped out — funding COMPRESSES sharply.

Trade: enter carry in the post-NFP period ONLY when NFP is risk-on + funding was pre-event
positive (carry confirmation). Skip or flip when NFP is risk-off + high-funding (compression risk).

## Structural reason (who is forced)
Risk-on NFP + already-long market = leveraged speculators ADD more long exposure (they were
right, they size up). This creates structural forced-buying of perp longs post-event, elevating
funding above baseline. They cannot defer — the news has already come out.

## Falsifier
(1) Post-NFP funding does NOT differ by surprise direction (direction agnostic = H-122 subsumes it).
(2) The funding × NFP-direction interaction is zero when BTC contemporaneous return is controlled
    (it's just return-correlated, not event-specific).
(3) eff-n: ~24 NFP events, conditioned on surprise direction split → ~12/12 → too low for
    the interaction test.

## Why uncaptured
Requires combining an economic calendar (BLS release dates), consensus estimates (public),
and actual figures (BLS) — modest data engineering. Low eff-n on the interaction. Large
funds trade this but at equity/FX level, not crypto funding-specific.

## Data status & effective-n
- data_status: HAVE (funding 8h, timestamps); NFP dates + consensus + actual HARDCODABLE from
  BLS public data and historical consensus (widely available). Need to look up ~24 NFP prints.
- eff-n: ~24 NFP events; split by direction → ~12 each. Low for interaction test.
- Feasibility: moderate — data engineering required (hardcode surprise column), but not BLOCKED.

## One-line test
Extend `funding_leads2.py`: hardcode NFP dates + surprise sign (±); extract funding in the
8h period after NFP; split by surprise direction; permute on ~12 events per direction;
compute carry EV conditioned on agreement (surprise_sign == funding_sign).
