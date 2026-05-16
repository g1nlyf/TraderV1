# Stage 2 Final Acceptance Report Export

Source database: `C:\Users\hacke\CascadeProjects\Finals1\TraderV1\WalletScarper\tmp\final_release_validation.sqlite3`
Final report row: `final_acceptance_report_54ebabb37daf4a798870fe204dc7f68d`
Acceptance run: `acceptance_run_f36b96f9cc924ba89e5dddc693734b17`
Generated at: `2026-05-15T13:54:19.164802+00:00`

## Decision

- Run mode: `fixture_replay`
- Acceptance run result: `gap_report_required`
- Final decision: `accepted_with_gaps`
- Shadow status: `gap_report_required`
- Shadow gap report: `shadow_gap_3e858fab1e104e6f99a73cdd6d5fa906`

## Invariants And Health

- Invariant status: `passed`
- Invariant findings: `0`
- Critical violations: `0`
- Failed fills: `1`
- Risk vetoes: `0`
- Degraded sources: `0`
- Net P&L: `4.8125625`
- Expectancy: `4.8125625`
- Drawdown: `0.0`

## Fixture Evidence

- signal_id: `signal_72dcaeb32e0344b9ac04cc67dfd5debf`
- no_trade_signal_id: `no_trade_signal_e78ef45037094bf68a43637a17bef80c`
- position_id: `paper_position_bc65c2c1d19f4f7f8794e16604670026`
- failed_fill_id: `paper_fill_ec66cdbef4db4202a4fd8bfd55f66eaa`
- outcome_id: `trade_outcome_2caf800564444c34b3c3afa6b9336d7d`
- review_id: `post_trade_review_b445dab37815453387edf42646e5da3e`
- memory_entry_id: `memory_entry_fc9bdeda66594a9b8e2bd3af36267a91`
- leaderboard_snapshot_ref: `strategy_metric_snapshot_c447cbfaccb6470aaf8a4e8e4a79646b`

## Strategy Result

- Strategy version: `strategy_version_f45cfc46a2174004a076774ee6ee05e7`
- Closed paper trade count: `1`
- Sample-size warning: `closed_trade_count 1 below required sample 5`
- Net P&L source: deterministic `trade_outcomes` fixture row, not a live profitability claim.
- Strategy decision: `insufficient_data` because `Insufficient deterministic closed paper trades.`

## Known Limitations

- No long-running production worker daemon was added.
- Partial exits remain unsupported.
- Shadow readiness is gap-reported unless quote freshness, latency, route quality, and fill comparison evidence exist.

## Raw JSON

See `final-acceptance-report.json` for the full exported database row.
