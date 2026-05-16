# Dust/SOL Calibration Note

Date: 2026-05-15

## DexScreener-Only Baseline

Operator-provided Dust/SOL result:

- token mint: `6veQU7HDdXV5DC2Eqhnri5q71gkMzG73qKkSSudnpump`
- pool address: `cxlnktczbdgtdh94luwginkdb6esa6ry2vqrdi1dvfhm`
- quote observations written: 10
- route-quality records written: 10
- failures: none
- status: `gap_report_required`
- gaps remaining: `fresh_high_confidence_quote_stream`, `fill_vs_quote_comparison`

Interpretation: DexScreener-only observation is useful source evidence, but it does not supply enough independent timestamp/spread/fill comparison evidence to claim Stage 3 readiness.

## All-Free Smoke

After wiring no-key independent sources, a one-sample `all_free` smoke wrote:

- sources attempted: DexScreener, GeckoTerminal, DexPaprika
- quote observations written: 3
- route-quality records written: 3
- failures: none
- status: `gap_report_required`
- gaps remaining in that smoke: `route_quality_model`, `fill_vs_quote_comparison`

Interpretation: independent no-key quote evidence is now stored. The route-quality gap remained open in the smoke because cross-source spread was too wide and route depth was insufficient under current gates. Fill-vs-quote remains open without a contemporaneous paper fill comparison.
