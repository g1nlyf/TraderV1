# 02. Target Market And Principles

## Initial market

Начальный рынок:

- Solana memecoins;
- не крупные криптоактивы;
- не ultra-fast pump/rug tokens, живущие секунды;
- не токены, где opportunity исчезает за 1-3 секунды;
- предпочтительно токены, живущие хотя бы несколько часов;
- токены с анализируемыми holders, wallets, liquidity, volume, market cap, lifecycle and participant behavior.

## Why Solana memecoins

Причина выбора не в том, что рынок "легкий". Напротив, он шумный и рискованный. Но он подходит для research system, потому что:

- много on-chain событий;
- видны wallets and transactions;
- lifecycle токенов часто короткий, но наблюдаемый;
- возможны повторяющиеся patterns по wallets, liquidity and holder distribution;
- можно строить real-market paper trading без реального исполнения.

## Excluded tokens

The final Stage 2 system scope, with Stage 3-compatible shadow design, excludes:

- tokens with opportunity windows shorter than the system can observe and simulate;
- tokens without reliable market snapshots;
- tokens with insufficient liquidity for realistic fills;
- obvious rug/noise candidates;
- tokens where estimated slippage dominates expected edge;
- tokens whose data quality is too low for evaluation.

## Initial priors

Initial priors не являются правилами:

- holder count buckets may matter;
- lower/mid holder counts may make wallet behavior easier to analyze;
- 3-10 strong wallets may help signal quality;
- 5-60 minute wallet holding time may be more copyable than seconds;
- slow memecoins may suit LLM-assisted research better than second-level pumps.

Каждый prior должен стать experiment dimension.

## Buckets to test

Система должна сравнивать:

- holder count buckets;
- liquidity buckets;
- market cap buckets;
- token age buckets;
- volume buckets;
- social activity buckets;
- wallet-quality buckets;
- transaction velocity buckets;
- top-holder concentration buckets;
- token lifecycle buckets.

## Market filter policy

Фильтры делятся на три типа:

1. **Hard safety veto:** токен не может быть paper traded, если данные или ликвидность не позволяют симулировать исполнение.
2. **Initial prior:** токен получает более высокий/низкий research priority, но не исключается навсегда.
3. **Learned filter:** фильтр доказал, что улучшает net expectancy on new paper trades.

Нельзя превращать priors в hard rules без evidence.

## Connection to positive expectancy

Market scope должен уменьшать шум и повышать вероятность найти testable edge. Если фильтр звучит разумно, но не улучшает net expectancy, он должен быть удален, ослаблен или перенесен в backlog экспериментов.
