"""
experiments.py — Module 7 of the Order Book + Market-Making Simulator.

The engine (Modules 1-6) can simulate one market-making session. This module
turns it into a RESEARCH tool: it runs many sessions and asks which strategies
and parameters actually win.

The core discipline here: NEVER trust a single run. One seed = one possible
market; its P&L is mostly noise. So every result is a MONTE CARLO average over
many seeds, reported with its spread. A strategy is good only if it wins on
average with acceptable variance -- exactly how a desk evaluates anything, and
the antidote to overfitting to one lucky backtest.

Tools:
  * monte_carlo(...)  -- average a config over N random markets
  * sweep(...)        -- vary one parameter, find the robust optimum
  * tournament(...)   -- rank named strategies by P&L and by risk-adjusted return

Runnable standalone:  python experiments.py
"""

import statistics

from informed import simulate


def monte_carlo(n_seeds=25, base_seed=1, **cfg):
    """Run `cfg` across n_seeds different random markets; summarize the outcomes."""
    pnls, max_inv, pickoffs, mo_informed = [], [], [], []
    for s in range(base_seed, base_seed + n_seeds):
        r = simulate(seed=s, **cfg)
        pnls.append(r["pnl"])
        max_inv.append(r["max_abs_inventory"])
        pickoffs.append(r["n_informed_fills"])
        mo_informed.append(r["markout_informed"])

    mean = statistics.mean(pnls)
    sd = statistics.pstdev(pnls)
    return {
        "mean_pnl": mean,
        "std_pnl": sd,
        # risk-adjusted return: mean P&L per unit of P&L volatility (Sharpe-like)
        "risk_adj": mean / sd if sd else float("inf"),
        "win_rate": sum(p > 0 for p in pnls) / len(pnls),
        "mean_max_inv": statistics.mean(max_inv),
        "mean_pickoffs": statistics.mean(pickoffs),
        "mean_markout_informed": statistics.mean(mo_informed),
        "n": n_seeds,
    }


def sweep(param, values, n_seeds=25, **base_cfg):
    """Vary one parameter over `values`; Monte-Carlo each; return a list of rows."""
    rows = []
    for v in values:
        cfg = dict(base_cfg)
        cfg[param] = v
        stats = monte_carlo(n_seeds=n_seeds, **cfg)
        stats[param] = v
        rows.append(stats)
    return rows


def tournament(strategies, n_seeds=25, **market_cfg):
    """
    Run each named strategy (a dict of MM params) across the SAME set of random
    markets and rank them. Returns rows sorted by mean P&L.
    """
    rows = []
    for name, params in strategies.items():
        cfg = dict(market_cfg)
        cfg.update(params)
        stats = monte_carlo(n_seeds=n_seeds, **cfg)
        stats["name"] = name
        rows.append(stats)
    rows.sort(key=lambda r: r["mean_pnl"], reverse=True)
    return rows


# ---------------------------------------------------------------------------
# Standalone demo.
# ---------------------------------------------------------------------------
# A toxic market: aggressive informed trader (low edge threshold), balanced noise.
TOXIC = dict(n_cycles=500, with_informed=True, edge=0.5, informed_size=5, p_buy=0.50)

if __name__ == "__main__":
    N = 25

    # --- 1) Why single runs lie: watch one config scatter across seeds ---
    print("\n############ Why we Monte-Carlo: one config, five different seeds ####")
    for s in (1, 2, 3, 4, 5):
        r = simulate(seed=s, half_spread=2, skew=0.3, **TOXIC)
        print(f"   seed {s}:  P&L {r['pnl']:+8.1f}")
    mc = monte_carlo(n_seeds=N, half_spread=2, skew=0.3, **TOXIC)
    print(f"   -> any ONE of those could mislead you. Over {N} seeds: "
          f"mean {mc['mean_pnl']:+.1f} +/- {mc['std_pnl']:.1f}, "
          f"win rate {mc['win_rate']:.0%}")

    # --- 2) Robust half-spread sweep (the widen-to-defend trade-off) ---
    print("\n############ Sweep: half-spread vs P&L in a toxic market ############")
    print("   half_spread |  mean P&L +/- std  | win% | avg pickoffs | risk-adj")
    for row in sweep("half_spread", [1, 2, 3, 4, 5, 6], n_seeds=N, skew=0.3, **TOXIC):
        print(f"        {row['half_spread']:>2}      | {row['mean_pnl']:+8.1f} "
              f"+/- {row['std_pnl']:>5.0f} | {row['win_rate']:>3.0%}  |    "
              f"{row['mean_pickoffs']:>5.1f}    |  {row['risk_adj']:+.2f}")
    print("   In THIS toxic market, widening helps strongly to ~4 then plateaus:")
    print("   defending against informed flow is worth more than the noise you lose.")
    print("   (A clean interior peak only shows up in LESS toxic markets -- try edge=2.)")

    # --- 3) Robust skew sweep (inventory control vs killing your edge) ---
    print("\n############ Sweep: inventory skew vs P&L and risk carried ##########")
    print("   skew |  mean P&L +/- std  | avg max inventory (risk)")
    for row in sweep("skew", [0.0, 0.1, 0.3, 0.6, 1.0], n_seeds=N,
                     half_spread=2, **TOXIC):
        print(f"   {row['skew']:>4} | {row['mean_pnl']:+8.1f} +/- {row['std_pnl']:>5.0f} "
              f"|        {row['mean_max_inv']:>5.1f}")
    print("   skew=0 (naive) carries the most inventory; more skew cuts risk but")
    print("   past a point flattens so eagerly it gives back the spread edge.")

    # --- 4) Strategy tournament ---
    print("\n############ Tournament: which market-maker wins? ##################")
    strategies = {
        "naive-tight":  dict(half_spread=1, skew=0.0),
        "naive-wide":   dict(half_spread=3, skew=0.0),
        "skewed-tight": dict(half_spread=1, skew=0.4),
        "skewed-wide":  dict(half_spread=3, skew=0.4),
        "balanced":     dict(half_spread=2, skew=0.3),
    }
    print("   strategy      |  mean P&L +/- std  | win% | risk-adj | avg max inv")
    for r in tournament(strategies, n_seeds=N, **TOXIC):
        print(f"   {r['name']:<13} | {r['mean_pnl']:+8.1f} +/- {r['std_pnl']:>5.0f} "
              f"| {r['win_rate']:>3.0%}  |  {r['risk_adj']:+.2f}   |   {r['mean_max_inv']:>5.1f}")
    print("   Ranked by mean P&L. Note the risk-adj column: the highest-P&L strategy")
    print("   isn't always the one you'd run -- a desk wants return PER unit of risk.")
