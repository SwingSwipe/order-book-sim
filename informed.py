"""
informed.py — Module 5b of the Order Book + Market-Making Simulator.

Adverse selection: the reason market-making is dangerous.

So far the market has been pure noise. Now we add:
  * a TRUE VALUE that drifts and occasionally JUMPS (news), and
  * an INFORMED TRADER who can see it and trades when the book is mispriced.

Your market-maker CANNOT see the true value -- it quotes around the stale mid.
So when the true value jumps, the informed trader lifts your (now too-cheap) ask
or hits your (now too-rich) bid right BEFORE the mid catches up. You get filled
on exactly the trades you'd rather not have done. That is ADVERSE SELECTION.

We measure it with the MARKOUT of each fill vs the true value at that instant:
    MM buys @ P  -> markout = qty * (true_value - P)   (negative = overpaid)
    MM sells @ P -> markout = qty * (P - true_value)   (negative = sold too cheap)
Against noise, markout ~ 0. Against an informed trader, it goes systematically
negative -- a number you can watch.

Runnable standalone:  python informed.py
"""

import random

from order_book import OrderBook
from flow import seed_book, step, FlowParams
from market_maker import run_market_making  # noqa: F401  (kept for parity/imports)
from smart_maker import SmartMarketMaker


class TrueValue:
    """
    The 'fair' price the asset is really worth. A random walk (diffusion) with
    occasional jumps standing in for news. The market only learns it through the
    informed trader's actions.
    """
    def __init__(self, start=100, vol=0.3, jump_prob=0.03, jump_size=4):
        self.value = float(start)
        self.vol = vol
        self.jump_prob = jump_prob
        self.jump_size = jump_size

    def step(self):
        self.value += random.gauss(0, self.vol)                  # quiet drift
        if random.random() < self.jump_prob:                     # news hits
            self.value += random.choice([-1, 1]) * self.jump_size
        return self.value


def informed_trade(book, true_value, size, edge):
    """
    The informed trader acts only when the book is mispriced by at least `edge`:
      * best ask well BELOW true value  -> the ask is cheap  -> BUY it (market order)
      * best bid well ABOVE true value  -> the bid is rich   -> SELL into it
    Otherwise it sits out. This is what informed flow looks like: it shows up
    precisely when the quotes are wrong, and it's on the right side when it does.
    """
    ask, bid = book.best_ask(), book.best_bid()
    if ask is not None and true_value >= ask + edge:
        book.add_market_order("bid", size)      # buy the cheap offer
    elif bid is not None and true_value <= bid - edge:
        book.add_market_order("ask", size)      # sell the rich bid


def _markout(fill, true_value):
    """Value of one MM fill vs true value right now. Negative = adversely selected."""
    if fill["side"] == "bid":                   # MM bought
        return fill["qty"] * (true_value - fill["price"])
    return fill["qty"] * (fill["price"] - true_value)   # MM sold


def run_informed_market(book, mm, n_cycles, true_value, flow_params=None,
                        flow_per_cycle=2, informed_size=5, edge=1.0,
                        with_informed=True, seed=None):
    """
    One cycle: true value evolves -> noise flow trades -> (optionally) the informed
    trader acts -> the MM books its fills. We markout the NOISE fills and the
    INFORMED fills separately, so the adverse selection shows up cleanly.
    """
    if seed is not None:
        random.seed(seed)
    flow_params = flow_params or FlowParams(p_buy=0.50)

    mo_noise = 0.0            # markout on fills that came from noise flow
    mo_informed = 0.0         # markout on fills that came from the informed trader
    n_informed_fills = 0
    pickoffs = []             # worst informed fills, for a "caught in the act" view
    pnl_hist, inv_hist = [], []

    mm.requote()
    for _ in range(n_cycles):
        tv = true_value.step()

        for _ in range(flow_per_cycle):          # noise trades against the book
            step(book, flow_params)
        for f in mm.reconcile():                 # book & markout the noise fills
            mo_noise += _markout(f, tv)

        if with_informed:
            informed_trade(book, tv, informed_size, edge)
            for f in mm.reconcile():             # book & markout the informed fills
                m = _markout(f, tv)
                mo_informed += m
                n_informed_fills += 1
                pickoffs.append((f, tv, m))

        pnl_hist.append(mm.pnl())
        inv_hist.append(mm.inventory)
        mm.requote()
    mm.reconcile()

    pickoffs.sort(key=lambda x: x[2])            # most negative markout first
    return {
        "pnl": mm.pnl(),
        "cash": mm.cash,
        "inventory": mm.inventory,
        "true_value": true_value.value,
        "mid": book.mid(),
        "markout_noise": mo_noise,
        "markout_informed": mo_informed,
        "n_informed_fills": n_informed_fills,
        "worst_pickoffs": pickoffs[:4],
        "pnl_hist": pnl_hist,
        "inv_hist": inv_hist,
    }


def _fresh_mm():
    book = OrderBook()
    seed_book(book, ref_price=100, levels=5, depth=10)
    mm = SmartMarketMaker(book, half_spread=1, quote_size=5,
                          skew=0.3, max_inventory=40, vol_coef=0.5)
    return book, mm


# ---------------------------------------------------------------------------
# Standalone demo.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # --- Part 1: decompose WHERE the money comes from and goes to ---
    # One market: balanced noise + an informed trader. We split the markout of
    # the MM's fills by who traded against it. Both are measured against the SAME
    # true value, which the informed trader keeps the mid tethered to -- so the
    # comparison is apples-to-apples (unlike a noise-only world, where nothing
    # links the mid to true value and the markout is meaningless).
    print("\n############ Where a market-maker's money comes from and goes ############")
    book, mm = _fresh_mm()
    B = run_informed_market(book, mm, n_cycles=500, true_value=TrueValue(start=100),
                            with_informed=True, seed=1)
    print(f"   fills vs NOISE traders:   markout {B['markout_noise']:+8.1f}   "
          f"<-- POSITIVE: noise pays you the spread")
    print(f"   fills vs INFORMED trader: markout {B['markout_informed']:+8.1f}   "
          f"<-- NEGATIVE: you get picked off ({B['n_informed_fills']} fills)")
    print("   i.e. you earn your edge from uninformed flow and bleed it back to")
    print("   informed flow. Net survival depends on which dominates.")

    print("\n   Caught in the act -- your worst pick-offs by the informed trader:")
    for fill, tv, m in B["worst_pickoffs"]:
        act = "you SOLD  " if fill["side"] == "ask" else "you BOUGHT"
        print(f"      {act} {fill['qty']}@{fill['price']} but true value was "
              f"{tv:.1f}  ->  markout {m:+.1f}")

    # --- Part 2: the defense -- widen your spread to resist being picked off ---
    # An informed trader only trades when it has at least `edge` of mispricing.
    # Quote wider and you demand more edge to be hit, so fewer pick-offs land.
    print("\n############ The defense: widen the spread, resist adverse selection ####")
    print("   half_spread | informed fills | informed markout | total P&L")
    for hs in (1, 2, 3, 4):
        bk = OrderBook()
        seed_book(bk, ref_price=100, levels=5, depth=10)
        m = SmartMarketMaker(bk, half_spread=hs, quote_size=5,
                             skew=0.3, max_inventory=40, vol_coef=0.5)
        r = run_informed_market(bk, m, n_cycles=500, true_value=TrueValue(start=100),
                                with_informed=True, seed=1)
        print(f"        {hs:>2}      |      {r['n_informed_fills']:>4}      |   "
              f"{r['markout_informed']:>8.1f}     | {r['pnl']:+8.1f}")
    print("   Wider quotes = fewer pick-offs = less adverse selection. But quote")
    print("   TOO wide and noise traders skip you too, so you stop earning the")
    print("   spread. That trade-off -- edge vs adverse selection -- is the job.")
