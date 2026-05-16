# 08. Token Discovery, Triage And Market Context

## Discovery sources

Potential sources:

- GMGN, if API or browser access is available;
- Solana on-chain events;
- DEX/liquidity events;
- DexScreener/DexPaprika/GeckoTerminal-like sources, if available;
- volume changes;
- market cap changes;
- holder distribution changes;
- smart-wallet movement;
- social/narrative triggers;
- anomaly detection.

Each source must have source metadata: reliability, latency, rate limits, completeness and failure behavior.

## API-first, browser-second policy

Use structured APIs/indexers first. Use browser research only when API access is unavailable, incomplete or needed for human-facing context such as GMGN pages or social/community views.

Browser-derived facts must create `BrowserExtraction` and/or `ContextSnapshot`, not canonical P&L facts.

Required browser fields:

- source URL;
- extraction timestamp;
- parser/version;
- raw HTML/screenshot/snapshot reference where practical;
- extracted fields;
- confidence score;
- degradation reason if extraction fails.

If a website changes layout, browser adapter must fail closed or lower confidence. It must not silently produce normal-looking but wrong data.

## Discovery output

`TokenCandidate` should include:

- token mint;
- pool address if known;
- source;
- discovered_at;
- source_timestamp;
- liquidity snapshot;
- volume snapshot;
- tx activity;
- market cap estimate;
- holder count if available;
- source confidence.

## Triage objective

Triage is not "find the best token". Triage decides which candidates deserve deeper analysis or paper-trading consideration. Its job is to reduce noise without hardcoding untested beliefs.

## Triage buckets

The system should evaluate performance by:

- holder count bucket;
- liquidity bucket;
- market cap bucket;
- token age bucket;
- volume bucket;
- tx velocity bucket;
- social activity bucket;
- wallet-quality bucket;
- top-holder concentration bucket.

Bucket boundaries must be configurable and versioned.

## Risk veto examples

Triage or risk layer may veto:

- insufficient liquidity;
- no reliable price source;
- data too stale;
- impossible simulated fill;
- obvious honeypot/rug-like behavior where detectable;
- extreme holder concentration;
- execution cost greater than plausible edge.

## Market context

Market Context Layer stores:

- SOL/crypto market regime;
- Solana network conditions;
- liquidity conditions;
- volatility state;
- route quality;
- broader risk-on/risk-off context;
- recent memecoin market behavior.

LLM can describe regimes, but deterministic metrics must store the structured state.

## Social and narrative research

Sources:

- Twitter/X;
- news;
- token communities;
- influencer mentions;
- social velocity;
- broader Solana ecosystem context.

Social signals are noisy. They can be used as context or confirmation only after contribution to paper-trading expectancy is measured.

LLM is useful for:

- summarizing narratives;
- detecting contradiction;
- classifying sentiment;
- identifying suspicious coordination.

Structured metrics required:

- timestamp;
- source reliability;
- source reach;
- sentiment score if used;
- link to token outcome;
- contribution to signal calibration.

## Positive expectancy connection

Discovery and triage improve expectancy by:

- reducing attention spent on low-quality tokens;
- preventing untradeable tokens from entering paper trades;
- exposing strategy performance across token buckets;
- avoiding social-noise overreaction;
- making no-trade decisions measurable.
