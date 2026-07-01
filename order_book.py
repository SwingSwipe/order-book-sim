"""
order_book.py — Modules 1 & 2 of the Order Book + Market-Making Simulator.

Module 1 (the data structure): two sides (bids / asks) organized into PRICE
LEVELS, where orders at the same price wait in a TIME-ORDERED queue. Best price
first, then earliest arrival = PRICE-TIME PRIORITY.

Module 2 (the matching engine): when an incoming order CROSSES the opposite side,
match it against the resting orders and generate TRADES. This is how trades
actually happen, and where the bid/ask spread does its work.

Key matching ideas:
  * MAKER vs TAKER: the resting order "makes" liquidity; the incoming aggressive
    order "takes" it. Exchanges charge takers and rebate makers.
  * Trades print at the MAKER's (resting) price -> the taker can get price
    improvement. The book, not the aggressor, sets the trade price.
  * A limit order matches everything it crosses, then RESTS the remainder.
  * A MARKET order takes whatever price is available and never rests.

Runnable standalone:  python order_book.py
"""

from dataclasses import dataclass
from collections import deque
from itertools import count


# ---------------------------------------------------------------------------
# An order is the atomic unit of the book.
# ---------------------------------------------------------------------------
@dataclass
class Order:
    order_id: int     # unique id, assigned by the book so we can cancel it later
    side: str         # "bid" (buyer) or "ask" (seller)
    price: int        # price in TICKS (integers — see note in OrderBook below)
    quantity: int     # how many units this order still wants to trade

    def __repr__(self):
        return f"Order(#{self.order_id} {self.side} {self.quantity}@{self.price})"


# ---------------------------------------------------------------------------
# A trade is what the matching engine produces when two orders cross.
# ---------------------------------------------------------------------------
@dataclass
class Trade:
    price: int        # the MAKER's price — where the trade actually printed
    quantity: int     # how many units changed hands in this fill
    taker_id: int     # the aggressive incoming order
    maker_id: int     # the resting order that got hit
    taker_side: str   # "bid" if the aggressor was buying, "ask" if selling

    def __repr__(self):
        aggressor = "BUY" if self.taker_side == "bid" else "SELL"
        return (f"Trade({self.quantity}@{self.price}  "
                f"{aggressor} #{self.taker_id} hit #{self.maker_id})")


class OrderBook:
    """
    A two-sided limit order book with a price-time-priority matching engine.

    Each side is a dict mapping  price -> deque of Orders  (a FIFO queue):

        bids = { 100: deque([Order, Order, ...]),   # buyers
                 99:  deque([Order]) }
        asks = { 101: deque([Order]),               # sellers
                 102: deque([Order, Order]) }

    Why this shape?
      * The dict gives O(1) access to "the queue at price P".
      * The deque keeps that level's orders in ARRIVAL ORDER, so the FRONT of the
        queue is the order with time priority — exactly who should fill first.
        Matching just pops from the front of the best-priced level.

    PRICES AS INTEGERS (ticks): real exchanges never store prices as floats
    (0.1 + 0.2 != 0.3, and floats make terrible dict keys). Every market has a
    TICK SIZE; prices are an integer number of ticks. We do the same.

    PERFORMANCE: best_bid/ask use max()/min() over the price keys — O(levels),
    fine for a sim. A production engine keeps levels in a sorted tree/heap for
    O(log n). We start readable and can swap the structure later.
    """

    def __init__(self):
        self.bids = {}                 # price -> deque[Order]  (buy side)
        self.asks = {}                 # price -> deque[Order]  (sell side)
        self._next_id = count(1)       # an id generator: 1, 2, 3, ...
        self._index = {}               # order_id -> Order, for O(1) cancel lookup
        self.tape = []                 # every Trade ever printed (the "time & sales")
        self.last_price = None         # most recent trade price (a sim's "last")

    # -- writing to the book -------------------------------------------------

    def add_limit_order(self, side, price, quantity):
        """
        Submit a limit order. It first MATCHES against everything it crosses on
        the opposite side, then RESTS any unfilled remainder on the book.

        Returns (order_id, trades) where trades is the list of fills it generated
        (empty if it didn't cross anything and just rested).
        """
        if side not in ("bid", "ask"):
            raise ValueError(f"side must be 'bid' or 'ask', got {side!r}")
        if price <= 0:
            raise ValueError(f"price must be positive, got {price}")
        if quantity <= 0:
            raise ValueError(f"quantity must be positive, got {quantity}")

        order_id = next(self._next_id)
        incoming = Order(order_id, side, price, quantity)

        trades = self._match(incoming)        # try to trade first

        if incoming.quantity > 0:             # rest whatever didn't fill
            book = self.bids if side == "bid" else self.asks
            book.setdefault(incoming.price, deque()).append(incoming)
            self._index[order_id] = incoming
        return order_id, trades

    def add_market_order(self, side, quantity):
        """
        Submit a market order: trade at WHATEVER price is available, walking the
        book until filled or the opposite side is empty. A market order never
        rests — any unfilled remainder is simply dropped (liquidity ran out).

        This is a taste of Module 3 (order flow); a market buy is just a limit
        buy willing to pay any price.

        Returns (order_id, trades). Check `quantity - filled` if you care about
        whether it fully filled.
        """
        if side not in ("bid", "ask"):
            raise ValueError(f"side must be 'bid' or 'ask', got {side!r}")
        if quantity <= 0:
            raise ValueError(f"quantity must be positive, got {quantity}")

        order_id = next(self._next_id)
        incoming = Order(order_id, side, price=None, quantity=quantity)
        trades = self._match(incoming, market=True)
        return order_id, trades               # remainder (if any) does NOT rest

    def cancel(self, order_id):
        """
        Remove a resting order by id. Returns the cancelled Order, or None if the
        id isn't on the book (already filled/cancelled/never rested).

        Cancelling is half of real order flow — a market-maker (Module 4) pulls
        and re-posts its quotes every time the mid moves.
        """
        order = self._index.pop(order_id, None)
        if order is None:
            return None

        book = self.bids if order.side == "bid" else self.asks
        level = book[order.price]
        level.remove(order)            # O(k) within this one price level
        if not level:                  # level now empty -> drop the price key
            del book[order.price]
        return order

    # -- the matching engine -------------------------------------------------

    def _match(self, incoming, market=False):
        """
        Match an incoming order against the opposite side by price-time priority.
        Mutates `incoming.quantity` down as it fills. Returns the trades produced.

        A buy (bid) eats the ASKS from the lowest price up; it keeps going while
        its price is >= the best ask (or always, for a market order). A sell
        mirrors that against the bids from the highest price down.
        """
        trades = []
        if incoming.side == "bid":
            while incoming.quantity > 0 and self.asks:
                best = min(self.asks)                     # cheapest seller first
                if not market and incoming.price < best:  # no longer crosses
                    break
                trades += self._fill_against(incoming, self.asks, best)
        else:  # incoming is a sell
            while incoming.quantity > 0 and self.bids:
                best = max(self.bids)                     # highest buyer first
                if not market and incoming.price > best:  # no longer crosses
                    break
                trades += self._fill_against(incoming, self.bids, best)
        return trades

    def _fill_against(self, incoming, opposite_book, price):
        """
        Fill `incoming` against the FIFO queue resting at one price level.
        Walks the queue front-to-back (time priority) generating Trades, and
        cleans up fully-filled makers. Stops when the incoming order is exhausted
        or the level empties.
        """
        trades = []
        level = opposite_book[price]
        while incoming.quantity > 0 and level:
            resting = level[0]                            # front of queue = oldest
            fill_qty = min(incoming.quantity, resting.quantity)

            # The trade prints at the MAKER's (resting) price — price improvement
            # for the taker when they crossed by more than the spread.
            trade = Trade(price=price, quantity=fill_qty,
                          taker_id=incoming.order_id, maker_id=resting.order_id,
                          taker_side=incoming.side)
            trades.append(trade)
            self.tape.append(trade)
            self.last_price = price

            incoming.quantity -= fill_qty
            resting.quantity -= fill_qty
            if resting.quantity == 0:                     # maker fully filled
                level.popleft()
                self._index.pop(resting.order_id, None)

        if not level:                                     # level drained -> drop it
            del opposite_book[price]
        return trades

    # -- reading the book ----------------------------------------------------

    def best_bid(self):
        """Highest price a buyer is willing to pay (or None if no bids)."""
        return max(self.bids) if self.bids else None

    def best_ask(self):
        """Lowest price a seller will accept (or None if no asks)."""
        return min(self.asks) if self.asks else None

    def spread(self):
        """best_ask - best_bid: what a market-maker tries to capture."""
        bid, ask = self.best_bid(), self.best_ask()
        if bid is None or ask is None:
            return None
        return ask - bid

    def mid(self):
        """The 'fair' reference price: halfway between best bid and best ask."""
        bid, ask = self.best_bid(), self.best_ask()
        if bid is None or ask is None:
            return None
        return (bid + ask) / 2

    def depth_at(self, side, price):
        """Total quantity resting at a given price level (0 if the level is empty)."""
        book = self.bids if side == "bid" else self.asks
        level = book.get(price)
        return sum(o.quantity for o in level) if level else 0

    def resting_order_ids(self):
        """Ids of every order currently resting on the book (for cancels / iteration)."""
        return list(self._index)

    # -- seeing the book -----------------------------------------------------

    def display(self, levels=5):
        """
        Print the book like a real ladder: asks on top (cheapest ask at the
        bottom, nearest the spread), bids below (highest bid at the top, nearest
        the spread). The spread sits in the middle — how a trader reads it.
        """
        ask_prices = sorted(self.asks, reverse=True)[-levels:]   # lowest few
        bid_prices = sorted(self.bids, reverse=True)[:levels]    # highest few

        print("        price | qty")
        print("   ASKS (sellers)")
        for p in ask_prices:
            print(f"        {p:>5} | {self.depth_at('ask', p)}")

        spread = self.spread()
        tail = "" if spread is None else f"   (spread {spread}, mid {self.mid()})"
        last = "" if self.last_price is None else f"   last={self.last_price}"
        print(f"   ----------------{tail}{last}")

        print("   BIDS (buyers)")
        for p in bid_prices:
            print(f"        {p:>5} | {self.depth_at('bid', p)}")


# ---------------------------------------------------------------------------
# Standalone demo: run `python order_book.py` to watch trades happen.
# ---------------------------------------------------------------------------
def _print_trades(trades):
    if not trades:
        print("   (no trades — order rested)")
    for t in trades:
        print(f"   {t}")


if __name__ == "__main__":
    book = OrderBook()

    # --- Seed a resting book (no crossing yet, so everything rests) ---
    book.add_limit_order("bid", price=99,  quantity=5)
    book.add_limit_order("bid", price=100, quantity=10)
    book.add_limit_order("ask", price=101, quantity=2)    # order #3, first in line at 101
    book.add_limit_order("ask", price=101, quantity=3)    # order #4, behind it at 101
    book.add_limit_order("ask", price=102, quantity=8)

    print("\n--- Resting book ---")
    book.display()

    # --- 1) A marketable LIMIT buy that crosses ---
    # Buy 4 @ 101: crosses the asks. Price-time priority fills order #3 (2@101)
    # fully, then 2 of order #4's 3@101. It prints at 101 (the maker's price).
    print("\n--- Limit BUY 4 @ 101 (crosses) ---")
    _, trades = book.add_limit_order("bid", price=101, quantity=4)
    _print_trades(trades)
    book.display()
    print("   -> #3 fully filled & gone; #4 has 1 left at 101 (time priority held)")

    # --- 2) A MARKET buy that walks the book ---
    # Buy 6 at any price: takes the last 1@101, then 5@102. Never rests.
    print("\n--- MARKET BUY 6 (walks levels) ---")
    _, trades = book.add_market_order("bid", quantity=6)
    _print_trades(trades)
    book.display()
    print("   -> lifted the 101, then ate into 102; notice the mid/last moved up")

    # --- 3) Price improvement: aggressive SELL through the bids ---
    # Sell 12 @ 98: crosses both bid levels (100 then 99). Even though we'd accept
    # 98, we trade at the BIDDERS' prices (10@100, then 2@99) -- better for us,
    # the taker. 10 + 2 = 12 fully fills, so nothing rests at 98.
    print("\n--- Limit SELL 12 @ 98 (crosses both bid levels) ---")
    _, trades = book.add_limit_order("ask", price=98, quantity=12)
    _print_trades(trades)
    book.display()
    print("   -> traded 10@100 + 2@99 = 12 filled; the 99 level has 3 left, nothing rests at 98")

    print(f"\n--- Time & sales (the tape): {len(book.tape)} prints ---")
    for t in book.tape:
        print(f"   {t}")
