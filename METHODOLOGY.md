# Methodology & Design

This document explains how the Order Book + Market-Making Simulator is built, the
design decisions behind it, the models it uses, how strategies are evaluated, and
— importantly — what it does *not* do. The goal of the project is to understand
market microstructure by building it from scratch: to write a matching engine you
have to know exactly how a trade happens.

---

## 1. Architecture

The project follows a strict **engine / UI split**. All market logic lives in
plain Python modules with no framework dependencies; the Streamlit app only draws.

| Layer | File | Responsibility |
|---|---|---|
| Data structure | `order_book.py` | Limit order book + matching engine |
| Flow | `flow.py` | Random (Poisson) order-flow generator |
| Agent | `market_maker.py` | Baseline market-maker + P&L accounting |
| Risk | `smart_maker.py` | Inventory-aware market-maker |
| Adversary | `informed.py` | True value, informed trader, adverse-selection measurement |
| Visualization | `app.py` | Interactive Streamlit cockpit |
| Research | `experiments.py` | Monte Carlo sweeps + strategy tournament |

Every engine module is runnable standalone (`python <module>.py`) and prints a
self-contained demonstration of its concept.

---

## 2. The order book

The book is two dictionaries mapping **price → FIFO queue of orders**:

```
bids = { price: deque([Order, ...]) }   # buyers
asks = { price: deque([Order, ...]) }   # sellers
```

- The **dict** gives O(1) access to a price level (add/cancel land instantly).
- The **deque** preserves arrival order within a level, so the front of the queue
  is the order with the oldest timestamp.

This encodes **price-time priority** directly: matching always takes the best
price (`min(asks)` / `max(bids)`) and, within that level, the front of the queue.
Cancels are O(1) to locate via an `order_id → Order` index, then O(k) within the
single affected level.

**Prices are integers (ticks).** Real exchanges never store prices as floats:
floating point cannot represent values like 0.1 exactly, which makes floats unsafe
as dictionary keys. Every market defines a minimum price increment (tick size) and
represents prices as an integer number of ticks. The simulator does the same.

**Performance note.** Best-price lookup uses `min`/`max` over the price keys —
O(number of levels), which is fine for a simulation. A production matching engine
keeps levels in a sorted tree or heap for O(log n) access; the structure could be
swapped without touching the rest of the code.

---

## 3. The matching engine

Every incoming order attempts to **match before it rests**. A buy crosses when its
price ≥ best ask; a sell crosses when its price ≤ best bid. Crossing orders are
filled against the resting queue, best price first and oldest first, until the
incoming order is exhausted or no longer crosses; any remainder rests.

Three microstructure facts fall out of this design:

- **Maker / taker.** The resting order provided liquidity (maker); the incoming
  aggressive order removed it (taker).
- **Trades print at the maker's price.** The resting order sets the trade price, so
  a taker who crosses by more than the spread receives price improvement.
- **Market orders never rest.** They take whatever price is available and drop any
  unfilled remainder (liquidity exhausted).

Every fill is written to a `tape` (time & sales) with maker/taker ids, which is how
the market-maker later reconciles its own fills.

---

## 4. The order-flow model

Order flow is modeled as three competing **Poisson processes** — market orders,
limit orders, and cancellations — each with a relative rate. Because the
probability that a given Poisson clock fires next is (its rate ÷ total rate), one
simulation step reduces to: pick an event type weighted by rate, then act.

This is a **zero-intelligence model**: the agents have no strategy and no notion of
fair value. The point is that even purely random posting, taking, and cancelling
produces a realistic two-sided book with a spread, uneven depth, and a price that
follows a random walk driven by order-flow imbalance. Limit orders dominate market
orders, and cancellations are frequent — matching the empirical fact that most
orders are cancelled rather than filled.

---

## 5. The market-making model

### P&L decomposition
The central accounting identity the whole project is built to teach:

```
Total P&L = cash  +  inventory × fair_value
            ----     ----------------------
            trades   mark-to-market
```

With flat inventory, cash equals the captured spread (pure profit). The danger is
the mark-to-market term: a maker can capture spread all day and still lose money on
the inventory it was forced to accumulate. Fills are booked by **reconciling the
trade tape** by maker/taker id — the same way a real trading system books fills
from an exchange drop-copy feed.

### Inventory-aware quoting (`SmartMarketMaker`)
The risk-aware maker adds three behaviors, in the spirit of the Avellaneda–Stoikov
framework (without its stochastic-control math):

1. **Inventory skew.** Quotes are centered on a reservation price
   `reservation = fair_value − inventory × skew`, so a short book raises both quotes
   (buy back, stop selling) and a long book lowers them. The maker actively steers
   toward flat instead of passively accumulating.
2. **Volatility widening.** The half-spread grows with the recent standard deviation
   of the mid, demanding more edge per fill when the market is moving fast.
3. **Hard inventory cap.** Past a maximum absolute position, the maker stops quoting
   the side that would grow it — a risk limit that bounds worst-case exposure.

---

## 6. Adverse selection

`informed.py` introduces a hidden **true value** (a random walk with occasional
jumps standing in for news) and an **informed trader** who can see it. The trader
acts only when the book is mispriced relative to true value by more than an edge
threshold — buying a too-cheap offer or selling into a too-rich bid. The
market-maker cannot see the true value; it quotes around the stale mid, so it is
picked off precisely when the price is about to move.

Adverse selection is measured with the **markout** of each fill against the true
value at the moment of the fill:

```
maker buys @ P   →  markout = qty × (true_value − P)     (negative = overpaid)
maker sells @ P  →  markout = qty × (P − true_value)     (negative = sold too cheap)
```

Fills are attributed to noise flow versus informed flow so the two are measured
separately. The consistent result: markout is positive on noise flow (the maker
earns its spread) and negative on informed flow (the maker is picked off).

---

## 7. Evaluation methodology

**Single runs are not evidence.** One random seed is one possible market; its P&L is
dominated by noise. Every reported result is therefore a **Monte Carlo** average
over many seeds (`experiments.py`), summarized by mean, standard deviation, win
rate, and average inventory carried.

Strategies are ranked not only by mean P&L but by **risk-adjusted return**
(mean ÷ standard deviation, a Sharpe-like ratio). This matters: in testing, the
highest raw-P&L strategy carried far more inventory-risk and P&L volatility than a
skewed strategy that earned less but delivered roughly three times the return per
unit of risk with a much higher win rate. Raw P&L is not the objective; return per
unit of risk is.

### Selected findings
- Against toxic (informed-heavy) flow, tight quoting is a reliable loser; widening
  the spread cuts pick-offs sharply and restores profitability.
- A small amount of inventory skew reduces P&L volatility substantially at little
  cost to mean P&L; excessive skew flattens so aggressively it erodes the edge.
- Conclusions drawn from a single seed were overturned by the Monte Carlo average —
  a concrete demonstration of why single-backtest tuning overfits.

---

## 8. Limitations (what this is *not*)

This is a **learning and demonstration tool, not a trading system.**

- It is a self-contained simulation with **no connection to real markets** and no
  real or historical data. It cannot and does not make money.
- The flow model is stylized (zero-intelligence noise plus a single informed
  agent); real markets have many interacting strategic participants, latency, and
  richer order types.
- The book uses simple linear data structures and price-time priority only; it does
  not model pro-rata matching, hidden/iceberg orders, auctions, or fees/rebates
  beyond the maker/taker concept.
- The informed trader is a deliberate caricature of information asymmetry, not a
  calibrated model of real informed flow.
- Results are internally consistent and illustrate the correct qualitative
  mechanics; they are not claims about any real instrument or venue.

The value of the project is that building it requires understanding the mechanics a
trading desk actually operates on — the organization of a book, how trades happen,
where market-making profit comes from, and why inventory and adverse selection, not
the spread, determine whether a desk keeps what it makes.

---

## References / inspiration
- Avellaneda, M. & Stoikov, S. (2008), *High-frequency trading in a limit order book* — the reservation-price / inventory-skew intuition.
- Smith, Farmer, Gillemot & Krishnamurthy (2003), *Statistical theory of the continuous double auction* — the zero-intelligence order-flow model.
- Standard sell-side market-making concepts: maker/taker, price-time priority, adverse selection, markout, inventory risk.
