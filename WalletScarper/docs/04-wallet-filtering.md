# Wallet Filtering

Идеальный кошелек:

- торгует несколько токенов;
- имеет закрытые позиции;
- общий PnL положительный;
- winrate нормальный, но не подозрительно идеальный;
- median hold не меньше 5 минут;
- лучший диапазон holding - 15-180 минут;
- median buy желательно 100 USD+;
- не делает десятки сделок по одному токену;
- прибыль не вся от одного случайного токена;
- похож на ручного/полуручного трейдера.

Penalty/reject:

- median buy < 25 USD;
- unique tokens < 3;
- closed positions < 3;
- total volume < 150 USD;
- total PnL <= 0;
- one-token profit share > 55%;
- tx per token median > 10;
- median hold < 5 minutes;
- bot_score > 65;
- perfect winrate on small sample.

