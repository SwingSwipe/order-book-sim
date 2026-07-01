"""
market_maker.py — Module 4 of the Order Book + Market-Making Simulator.

You become the market-maker. You post a BID below fair value and an ASK above
it, the random order flow (Module 3) trades against your quotes, and we track
your INVENTORY and P&L. This is how a desk actually makes money: not by calling
direction, but by quoting both sides and capturing the spread -- while managing
the position it picks up along the way.

The two pieces of P&L (learn this cold):

    Total P&L = cash  +  inventory * fair_value
                ----     ----------------------
                from     mark-to-market: the position you're
                trades   currently stuck holding, valued at the mid

With FLAT inventory, cash == the spread you captured (pure profit). The danger
is mark-to-market: you can capture spread all day and still lose if the price
moves against the inventory you accumulated. That is inventory risk, and it's
the whole problem Module 5 (skewing quotes) exists to manage.

How fills are detected: the matching engine writes every Trade to book.tape with
the maker/taker ids. We RECONCILE against that tape -- exactly how a real trading
system books its fills from the exchange's trade feed. Any trade whose maker or
taker is one of our orders updates our inventory and cash.

Runnable standalone:  python market_maker.py
"""

from order_book import OrderBook
from flow import seed_book, step, FlowParams


class MarketMaker:
    """
    A simple two-sided market-maker. Each cycle it cancels its old quotes and
    re-posts a fresh bid/ask straddling fair value (the book mid).
    """

    def __init__(self, book, half_spread=1, quote_size=5):
        self.book = book
        self.half_spread = half_spread     # how far each quote sits from fair value
        self.quote_size = quote_size       # size we show on each side

        self.inventory = 0                 # net position: + = long, - = short
        self.cash = 0.0                    # buys lower it, sells raise it
        self.n_buys = 0                    # count of buy fills (we got hit on our bid)
        self.n_sells = 0                   # count of sell fills (lifted on our ask)

        self.bid_id = None                 # our currently resting quotes
        self.ask_id = None
        self._my_ids = set()               # every order id we've ever posted
        self._tape_seen = 0                # how far into book.tape we've reconciled

    # -- valuation -----------------------------------------------------------

    def fair_value(self):
        """Our reference 'true' price. We use the book mid; fall back to last."""
        m = self.book.mid()
        return m if m is not None else self.book.last_price

    def pnl(self):
        """Mark-to-market total P&L = cash + inventory valued at fair value."""
        fv = self.fair_value()
        mark = self.inventory * fv if fv is not None else 0.0
        return self.cash + mark

    # -- the two things a market-maker does: reconcile fills, then re-quote ---

    def reconcile(self):
        """
        Walk the new trades on the tape and book any that involved our orders.
        A trade tells us taker_side; if WE were the maker, our side is the
        opposite. Bought -> inventory up, cash down. Sold -> inventory down,
        cash up. Handles partial fills automatically (each fill is its own Trade).

        Returns the list of fills it booked, as dicts {side, price, qty} -- so a
        caller (Module 5b) can measure the markout of each fill against true value.
        """
        booked = []
        for trade in self.book.tape[self._tape_seen:]:
            if trade.taker_id in self._my_ids:
                my_side = trade.taker_side                       # we were aggressor
            elif trade.maker_id in self._my_ids:
                my_side = "ask" if trade.taker_side == "bid" else "bid"  # opposite
            else:
                continue                                         # not our trade

            if my_side == "bid":                                 # we BOUGHT
                self.inventory += trade.quantity
                self.cash -= trade.quantity * trade.price
                self.n_buys += 1
            else:                                                # we SOLD
                self.inventory -= trade.quantity
                self.cash += trade.quantity * trade.price
                self.n_sells += 1
            booked.append({"side": my_side, "price": trade.price,
                           "qty": trade.quantity})

        self._tape_seen = len(self.book.tape)
        return booked

    def quote_prices(self, fv):
        """Where to post. Module 4: symmetric around fair value. (Module 5 will
        skew these based on inventory.)"""
        bid_px = int(round(fv - self.half_spread))
        ask_px = int(round(fv + self.half_spread))
        if ask_px <= bid_px:                  # guarantee a real, positive spread
            ask_px = bid_px + 1
        return max(1, bid_px), max(2, ask_px)

    def requote(self):
        """Cancel stale quotes and post a fresh two-sided market around fair value."""
        if self.bid_id is not None:
            self.book.cancel(self.bid_id)     # cancel() is a no-op if already filled
        if self.ask_id is not None:
            self.book.cancel(self.ask_id)

        fv = self.fair_value()
        if fv is None:                        # nothing to anchor to yet
            self.bid_id = self.ask_id = None
            return

        bid_px, ask_px = self.quote_prices(fv)
        self.bid_id, _ = self.book.add_limit_order("bid", bid_px, self.quote_size)
        self.ask_id, _ = self.book.add_limit_order("ask", ask_px, self.quote_size)
        self._my_ids.add(self.bid_id)
        self._my_ids.add(self.ask_id)


def run_market_making(book, mm, n_cycles, flow_params=None,
                      flow_per_cycle=2, seed=None):
    """
    Interleave order flow with the market-maker's quoting loop:

        post quotes -> let some flow hit them -> reconcile fills -> re-quote ...

    Returns the per-cycle history of P&L and inventory (a time series you can
    plot in Module 6) plus a final summary.
    """
    import random
    if seed is not None:
        random.seed(seed)
    flow_params = flow_params or FlowParams()

    pnl_history = []
    inv_history = []

    mm.requote()                              # put our first quotes up
    for _ in range(n_cycles):
        for _ in range(flow_per_cycle):       # the market trades for a bit...
            step(book, flow_params)
        mm.reconcile()                        # ...then we book whatever hit us
        pnl_history.append(mm.pnl())
        inv_history.append(mm.inventory)
        mm.requote()                          # and refresh our quotes around the new mid
    mm.reconcile()                            # catch any final immediate-cross fills

    return {
        "cash": mm.cash,
        "inventory": mm.inventory,
        "fair_value": mm.fair_value(),
        "pnl": mm.pnl(),
        "n_buys": mm.n_buys,
        "n_sells": mm.n_sells,
        "pnl_history": pnl_history,
        "inv_history": inv_history,
    }


def _report(title, stats):
    fv = stats["fair_value"]
    mark = stats["inventory"] * fv if fv is not None else 0.0
    inv_path = stats["inv_history"]
    print(f"\n=== {title} ===")
    print(f"   fills:        {stats['n_buys']} buys / {stats['n_sells']} sells")
    print(f"   cash (captured spread):   {stats['cash']:+.1f}")
    print(f"   inventory:    {stats['inventory']:+d} units  @ fair value {fv}")
    print(f"   mark-to-mkt (inventory):  {mark:+.1f}")
    print(f"   ------------------------------------")
    print(f"   TOTAL P&L:    {stats['pnl']:+.1f}")
    if inv_path:
        print(f"   inventory ranged from {min(inv_path):+d} to {max(inv_path):+d} "
              f"(how much risk you carried)")


# ---------------------------------------------------------------------------
# Standalone demo: the same market-maker in two different worlds.
# ---------------------------------------------------------------------------
if __name__ == "__main__":

    # --- World 1: BALANCED flow (p_buy = 0.50) ---
    # Buyers and sellers arrive equally. The MM's inventory stays near zero and
    # it just harvests the spread. THIS is the clean "desk makes money" picture.
    book1 = OrderBook()
    seed_book(book1, ref_price=100, levels=5, depth=10)
    mm1 = MarketMaker(book1, half_spread=1, quote_size=5)
    stats1 = run_market_making(book1, mm1, n_cycles=600,
                               flow_params=FlowParams(p_buy=0.50),
                               seed=42)
    _report("World 1: balanced flow (p_buy=0.50)", stats1)

    # --- World 2: ONE-SIDED flow (p_buy = 0.62) ---
    # Persistent buying pressure. Buyers keep LIFTING the MM's ask, so the MM
    # keeps SELLING -> it accumulates a SHORT inventory while the price drifts UP.
    # Watch the spread capture look fine while the mark-to-market bleeds. This is
    # inventory risk / the seed of adverse selection -> the problem Module 5 fixes.
    book2 = OrderBook()
    seed_book(book2, ref_price=100, levels=5, depth=10)
    mm2 = MarketMaker(book2, half_spread=1, quote_size=5)
    stats2 = run_market_making(book2, mm2, n_cycles=600,
                               flow_params=FlowParams(p_buy=0.62),
                               seed=42)
    _report("World 2: one-sided flow (p_buy=0.62)", stats2)

    print("\n   Same strategy, two worlds. Notice how the inventory you're forced")
    print("   to carry -- not the spread you capture -- is what makes or breaks you.")
