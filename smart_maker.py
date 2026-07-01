"""
smart_maker.py — Module 5a of the Order Book + Market-Making Simulator.

The Module 4 market-maker quotes SYMMETRICALLY around fair value, so one-sided
flow walks it into a huge position and it gets run over (World 2: +21k cash but
-5,225 net, short 152 units). This module gives it risk instincts:

  1. INVENTORY SKEW — quote around a "reservation price" that leans against your
     position, so you actively steer back toward flat instead of piling on.
         reservation = fair_value - inventory * skew
     Short -> reservation up -> bid higher (buy back), ask higher (stop selling).
     Long  -> reservation down -> sell eagerly, buy reluctantly.
     (This is the Avellaneda-Stoikov idea, minus the calculus.)

  2. VOLATILITY WIDENING — when recent price moves are large, widen your spread.
     Fast market = more chance of being picked off = demand more edge per fill.

  3. INVENTORY CAP — a hard risk limit: past a max position, stop quoting the
     side that would grow it. This is what turns a bad day into a survivable one.

Everything else (fill reconciliation, P&L) is inherited from MarketMaker.

Runnable standalone:  python smart_maker.py
"""

from collections import deque
from statistics import pstdev

from order_book import OrderBook
from flow import seed_book, FlowParams
from market_maker import MarketMaker, run_market_making, _report


class SmartMarketMaker(MarketMaker):
    def __init__(self, book, half_spread=1, quote_size=5,
                 skew=0.3, max_inventory=40, vol_coef=0.5, vol_window=20):
        super().__init__(book, half_spread, quote_size)
        self.skew = skew                        # ticks of quote shift per unit inventory
        self.max_inventory = max_inventory      # hard position limit
        self.vol_coef = vol_coef                # how much to widen per unit of vol
        self._mids = deque(maxlen=vol_window)   # recent fair values, for the vol estimate

    def recent_vol(self):
        """Std dev of recent tick-to-tick fair-value changes. 0 until we have data."""
        if len(self._mids) < 2:
            return 0.0
        diffs = [self._mids[i] - self._mids[i - 1] for i in range(1, len(self._mids))]
        return pstdev(diffs)

    def quote_prices(self, fv):
        """
        Skew around a reservation price, and widen the half-spread with volatility.
        This overrides the symmetric version in MarketMaker.
        """
        reservation = fv - self.inventory * self.skew       # lean against inventory
        hs = self.half_spread + self.vol_coef * self.recent_vol()  # widen when choppy
        bid_px = int(round(reservation - hs))
        ask_px = int(round(reservation + hs))
        if ask_px <= bid_px:                                 # keep a real spread
            ask_px = bid_px + 1
        return max(1, bid_px), max(2, ask_px)

    def requote(self):
        """
        Cancel stale quotes and re-post. Unlike the base class this can go
        ONE-SIDED: if we're at the long cap we stop bidding; at the short cap we
        stop asking. That's the risk limit doing its job.
        """
        if self.bid_id is not None:
            self.book.cancel(self.bid_id)
        if self.ask_id is not None:
            self.book.cancel(self.ask_id)
        self.bid_id = self.ask_id = None

        fv = self.fair_value()
        if fv is None:
            return
        self._mids.append(fv)                                # feed the vol estimate

        bid_px, ask_px = self.quote_prices(fv)
        if self.inventory < self.max_inventory:              # not too long -> ok to buy
            self.bid_id, _ = self.book.add_limit_order("bid", bid_px, self.quote_size)
            self._my_ids.add(self.bid_id)
        if self.inventory > -self.max_inventory:             # not too short -> ok to sell
            self.ask_id, _ = self.book.add_limit_order("ask", ask_px, self.quote_size)
            self._my_ids.add(self.ask_id)


# ---------------------------------------------------------------------------
# Standalone demo: naive vs smart maker in a balanced world and a one-sided one.
# ---------------------------------------------------------------------------
def _run(maker_kind, flow_params):
    """Build a fresh book + maker of the given kind and run it. Returns stats."""
    book = OrderBook()
    seed_book(book, ref_price=100, levels=5, depth=10)
    if maker_kind == "naive":
        mm = MarketMaker(book, half_spread=1, quote_size=5)
    else:
        mm = SmartMarketMaker(book, half_spread=1, quote_size=5,
                              skew=0.3, max_inventory=40, vol_coef=0.5)
    return run_market_making(book, mm, n_cycles=600, flow_params=flow_params, seed=42)


def _line(label, s):
    inv = s["inv_history"]
    rng = f"[{min(inv):+d},{max(inv):+d}]" if inv else "n/a"
    print(f"   {label:<8} P&L {s['pnl']:+9.1f}   ending inv {s['inventory']:+5d}   "
          f"range {rng:>10}   (cash {s['cash']:+.0f})")


if __name__ == "__main__":
    print("\n############ BALANCED flow (p_buy=0.50) -- normal, noisy market ############")
    _line("naive", _run("naive", FlowParams(p_buy=0.50)))
    _line("smart", _run("smart", FlowParams(p_buy=0.50)))
    print("   -> Naive made more absolute P&L here (+266 vs +15) -- but only by")
    print("      carrying up to -51 inventory that HAPPENED not to blow up. Smart made")
    print("      less on a fraction of the risk ([-6,+6]). Risk-adjusted, smart wins;")
    print("      and the naive 'edge' is really just uncompensated risk waiting to bite.")

    print("\n############ ONE-SIDED flow (p_buy=0.62) -- relentless buying #############")
    _line("naive", _run("naive", FlowParams(p_buy=0.62)))
    _line("smart", _run("smart", FlowParams(p_buy=0.62)))
    print("   -> Neither MAKES money: one-sided flow is adverse -- you're always on")
    print("      the wrong side. But smart slashes the loss and keeps inventory tiny")
    print("      instead of ending -152. Risk control turns a blow-up into a bad day.")
    print("\n   This is the cliffhanger for Module 5b: WHY is one-sided flow so toxic?")
    print("   Because it behaves like an INFORMED trader who knows where price is going.")
