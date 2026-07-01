# Order Book + Market-Making Simulator

A from-scratch **limit order book, matching engine, and market-making simulator**
built to understand how a trading desk actually makes money — market microstructure
from the ground up. Self-contained: no external data, no API keys.

Why this exists: sales & trading is fundamentally about *making markets* — quoting
a bid and an ask, capturing the spread, and managing the inventory and risk you
pick up. Building the machine is the fastest way to actually understand it: to code
a matching engine you have to know exactly how a trade happens.

## Modules (built in order — each forces a microstructure concept)

1. **Order book structure** — two-sided book (bids/asks) as price levels with
   time-ordered queues. Teaches price-time priority. `order_book.py`
2. **Matching engine** — crossing orders match by price-time priority and print
   trades. Teaches maker/taker, the spread, price improvement. `order_book.py`
3. **Order flow simulator** — Poisson-driven stream of market/limit/cancel events
   so the book lives on its own. Teaches liquidity and what flow looks like. `flow.py`
4. **Market-maker agent** — post a bid and ask around fair value, capture the
   spread, track inventory and P&L. Teaches how a desk makes money. `market_maker.py`
5. **Risk & inventory management** — skew quotes by inventory, widen in volatility,
   survive adverse selection (informed flow). *(in progress)*
6. **Analytics / visualization** — book depth, P&L curve, inventory over time. *(planned)*
7. **Experiments** — compare market-making strategies vs an informed trader. *(planned)*

## Run it

```bash
python order_book.py     # Modules 1-2: book + matching engine demo
python flow.py           # Module 3: a random market coming to life
python market_maker.py   # Module 4: the market-maker in a balanced vs one-sided world
```

## The one idea to take away

**Total P&L = cash (captured spread) + inventory × fair value (mark-to-market).**
Capturing spread is not profit — the inventory you're forced to hold is the risk
that decides whether you keep it. That tension is the entire job.

Python 3, standard library only (pandas / Streamlit come in with the analytics module).
