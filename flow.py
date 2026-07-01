"""
flow.py — Module 3 of the Order Book + Market-Making Simulator.

The matching engine (Module 2) only does something when YOU feed it an order.
This module feeds it a STREAM of random orders so the book lives on its own.

We model order flow as three Poisson processes competing to fire next:
    * MARKET orders   — take liquidity (cross the spread)
    * LIMIT orders    — make liquidity (rest, or cross if aggressive)
    * CANCELS         — pull a resting order (most real orders end this way)

The key fact that makes this simple: when several Poisson clocks tick, the
chance a given one fires NEXT is just (its rate / the total rate). So one step
of the simulation = "pick an event type weighted by its rate, then act."

This is a ZERO-INTELLIGENCE model: the agents have no strategy and no notion of
fair value — they trade randomly. The point is to see that even pure noise builds
a realistic two-sided book. In Modules 5/7 we add an INFORMED trader with a view,
which is what lets a market-maker get picked off (adverse selection).

Runnable standalone:  python flow.py
"""

import random
from dataclasses import dataclass

from order_book import OrderBook


# ---------------------------------------------------------------------------
# All the knobs of the flow in one place. Rates are RELATIVE weights, not
# absolute times — only their ratios matter (rate / total = P(fire next)).
# ---------------------------------------------------------------------------
@dataclass
class FlowParams:
    rate_market: float = 1.0     # how often takers hit the book
    rate_limit: float = 5.0      # how often makers post (limits dominate real flow)
    rate_cancel: float = 3.0     # how often resting orders get pulled
    p_buy: float = 0.50          # P(an order is a buy). 0.5 = balanced flow.
    max_size: int = 5            # order sizes drawn uniformly from 1..max_size
    geo_p: float = 0.50          # controls how tightly limits cluster at the touch


def _geo(p):
    """
    A small non-negative integer offset, geometrically distributed: 0 is most
    likely, larger values fall off fast. P(0)=p, P(1)=p(1-p), ... (capped at 6).
    This is how far from the touch a new limit order lands: usually right at the
    inside, occasionally deeper in the book.
    """
    k = 0
    while random.random() > p and k < 6:
        k += 1
    return k


def _ref_price(book, fallback):
    """A reference 'fair' price to anchor orders to when a side is missing."""
    m = book.mid()
    if m is not None:
        return m
    if book.last_price is not None:
        return book.last_price
    return fallback


def _limit_price(book, side, fallback, params):
    """
    Choose a price for a new limit order, anchored to the current touch.

    A BUY posts at best_bid + 1 - offset:
        offset 0 -> best_bid + 1  (IMPROVES the bid; if spread is 1 tick this
                                   equals best_ask and the order CROSSES -> trades)
        offset 1 -> best_bid      (JOINS the back of the queue at the touch)
        offset 2+-> deeper        (adds depth behind the market)
    A SELL mirrors that at best_ask - 1 + offset. So flow naturally tightens,
    widens, joins, and occasionally crosses — exactly what a real book does.
    """
    off = _geo(params.geo_p)
    if side == "bid":
        base = book.best_bid()
        if base is None:
            base = max(1, round(_ref_price(book, fallback)) - 1)
        price = base + 1 - off
    else:
        base = book.best_ask()
        if base is None:
            base = round(_ref_price(book, fallback)) + 1
        price = base - 1 + off
    return max(1, price)          # prices must stay positive


def seed_book(book, ref_price=100, levels=5, depth=10):
    """
    Plant an initial symmetric book around ref_price so the simulation starts
    from a real two-sided market (you can't have flow with nothing to trade
    against). Bids below ref, asks above, `depth` units per level.
    """
    for i in range(1, levels + 1):
        book.add_limit_order("bid", price=ref_price - i, quantity=depth)
        book.add_limit_order("ask", price=ref_price + i, quantity=depth)
    return book


def step(book, params, fallback=100):
    """
    Generate and apply ONE random flow event. Returns a small dict describing it
    (handy for logging / later analytics). This is the heart of the simulator.
    """
    # Cancels are only possible if something is resting; otherwise zero that clock.
    resting = book.resting_order_ids()
    r_cancel = params.rate_cancel if resting else 0.0
    total = params.rate_market + params.rate_limit + r_cancel
    roll = random.random() * total

    side = "bid" if random.random() < params.p_buy else "ask"
    size = random.randint(1, params.max_size)

    if roll < params.rate_market:
        # MARKET order: take liquidity at any price.
        _, trades = book.add_market_order(side, size)
        filled = sum(t.quantity for t in trades)
        return {"type": "market", "side": side, "size": size,
                "filled": filled, "trades": len(trades)}

    elif roll < params.rate_market + params.rate_limit:
        # LIMIT order: post near the touch; may rest or cross.
        price = _limit_price(book, side, fallback, params)
        _, trades = book.add_limit_order(side, price, size)
        filled = sum(t.quantity for t in trades)
        return {"type": "limit", "side": side, "size": size, "price": price,
                "filled": filled, "trades": len(trades)}

    else:
        # CANCEL: pull a random resting order.
        victim = random.choice(resting)
        cancelled = book.cancel(victim)
        return {"type": "cancel", "order_id": victim,
                "side": cancelled.side, "price": cancelled.price}


def run(book, n_steps, params=None, seed=None, verbose=0, fallback=100):
    """
    Run the simulator for n_steps events and return summary stats.

    seed     : fix the RNG for a reproducible run (essential for a sim you want
               to debug or compare strategies against later).
    verbose  : print the first `verbose` events so you can watch the flow.
    """
    params = params or FlowParams()
    if seed is not None:
        random.seed(seed)

    counts = {"market": 0, "limit": 0, "cancel": 0}
    n_trades = 0          # number of individual fills
    volume = 0            # total units traded
    mid_history = []      # mid after each step (a price path you can plot later)

    for i in range(n_steps):
        ev = step(book, params, fallback)
        counts[ev["type"]] += 1
        n_trades += ev.get("trades", 0)
        volume += ev.get("filled", 0)
        m = book.mid()
        if m is not None:
            mid_history.append(m)

        if i < verbose:
            print(f"   step {i:>3}: {ev}")

    return {
        "steps": n_steps,
        "counts": counts,
        "n_trades": n_trades,
        "volume": volume,
        "last_price": book.last_price,
        "spread": book.spread(),
        "mid": book.mid(),
        "resting_orders": len(book.resting_order_ids()),
        "mid_history": mid_history,
    }


# ---------------------------------------------------------------------------
# Standalone demo: run `python flow.py` to watch a market come to life.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    book = OrderBook()
    seed_book(book, ref_price=100, levels=5, depth=10)

    print("\n--- Seeded book (before any flow) ---")
    book.display()

    params = FlowParams()
    print(f"\n--- Running 300 events (seed=7); first 10 shown ---")
    stats = run(book, n_steps=300, params=params, seed=7, verbose=10)

    print("\n--- Book after the flow ---")
    book.display()

    print("\n--- Summary ---")
    print(f"   events: {stats['counts']}")
    print(f"   fills: {stats['n_trades']}   volume traded: {stats['volume']} units")
    print(f"   ending spread: {stats['spread']}   mid: {stats['mid']}   "
          f"last: {stats['last_price']}")
    print(f"   orders still resting: {stats['resting_orders']}")

    path = stats["mid_history"]
    if path:
        print(f"   mid wandered from {path[0]} to {path[-1]} "
              f"(low {min(path)}, high {max(path)}) -- a random walk, no fair value")
