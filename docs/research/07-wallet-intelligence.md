# 07. Wallet Intelligence Design

## Core definition

Wallet Intelligence Agent is not a wallet scraper. It is a research and validation layer that asks:

> Does this wallet's behavior improve system net expectancy on new paper trades?

A good wallet is not a wallet with a beautiful history. A good wallet is a wallet whose signals statistically improve net expectancy in forward, realistic paper trading.

## Candidate wallet discovery

Candidate wallets may come from:

- early buyers in selected tokens;
- profitable exits in reconstructed token trades;
- repeated participation across successful token buckets;
- wallets seen before liquidity expansion;
- wallets followed by other wallets;
- wallets triggering paper wins in prior strategy versions;
- external references such as GMGN links, if accessible.

Discovery is not validation. Discovery only creates candidates.

## Trade reconstruction

For each wallet, reconstruct:

- token entries;
- exits;
- partial exits;
- adds / reductions;
- realized P&L;
- unrealized inventory;
- fees estimate;
- slippage estimate where applicable;
- holding time;
- position size;
- token context at entry and exit.

If data is incomplete, the system must lower evidence quality instead of inventing missing facts.

## Wallet metrics

Required:

- realized P&L;
- unrealized P&L;
- net P&L after costs;
- win rate;
- expectancy;
- payoff ratio;
- average win / average loss;
- max drawdown;
- holding time distribution;
- position sizing distribution;
- token selection quality;
- entry quality;
- exit quality;
- repeatability;
- degradation of edge;
- sample size and recency.

## Behavior classification

Possible labels:

- insider;
- sniper;
- smart money;
- whale;
- market maker;
- farm wallet;
- noisy wallet;
- copy-trader;
- coordinated cluster;
- manipulative wallet;
- unknown / insufficient evidence.

Labels require evidence and confidence. They are not permanent identities.

## User intuition as priors

Initial wallet priors:

- not a seconds-level sniper/scalper;
- holding time roughly 5-60 minutes may be more copyable;
- positive P&L;
- not thousands of chaotic microtransactions;
- entered relatively early and exited relatively late;
- adds/partial exits allowed if they improve results.

These are priors, not rules. They must be tested against net expectancy.

## Cluster detection

The system should identify:

- related wallets;
- repeated same-token synchronized entries;
- synchronized exits;
- wallets funded by same sources, if data allows;
- copy-trading chains;
- farm-like behavior;
- manipulative clusters.

Cluster signals should be used carefully. A cluster may indicate real information flow or pure manipulation.

## Ranking methodology

Wallet ranking should combine:

- cost-adjusted P&L metrics;
- consistency across tokens;
- forward paper contribution;
- signal freshness;
- holding time copyability;
- liquidity compatibility;
- degradation tracking;
- evidence quality;
- cluster risk penalties;
- manipulation/noise penalties.

The ranking must include explanation:

- why included;
- why excluded;
- what evidence is weak;
- what would demote the wallet;
- whether signals improved paper P&L.

## Validation through paper trading

No wallet becomes trusted from historical analysis alone. Validation requires:

1. wallet signal observed in real time;
2. decision timestamped before result;
3. paper entry simulated without hindsight;
4. exit logic predefined;
5. net P&L after costs calculated deterministically;
6. wallet contribution measured against baseline.

## Failure modes

- lucky wallet problem;
- insider wallet that cannot be copied;
- wallet becomes popular and edge degrades;
- farm wallets designed to look profitable;
- copy-trader chain mistaken for original signal;
- incomplete history causing inflated P&L;
- overfitting to one token or one market regime.

## Positive expectancy connection

Wallet intelligence is useful only if wallet-derived signals improve forward paper net expectancy. Historical wallet attractiveness is not enough.

