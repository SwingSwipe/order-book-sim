"""
app.py — the interactive cockpit (Modules 6 & 8, plus a Research view over Module 7).

Three views:
  * Simulator  — set your quoting strategy and the market's toxicity, run one
    session, and see book depth, P&L, inventory, price vs the hidden true value,
    and where the money came from and went. Includes one-click guided scenarios.
  * Research   — Monte Carlo over many random markets: the widen-to-defend curve
    and a strategy tournament ranked by risk-adjusted return.
  * Learn      — plain-English concept explanations + an interactive self-quiz.

Engine/UI split: all logic lives in the engine modules; this file only draws.

Run:  python -m streamlit run app.py     (or the preview server, port 8504)
"""

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from informed import simulate
from experiments import sweep, tournament
from teach import CONCEPTS, QUIZ

st.set_page_config(page_title="Order Book + Market-Making Sim", layout="wide")

GREEN, RED, BLUE, GREY = "#16a34a", "#dc2626", "#2563eb", "#9ca3af"


# ---------------------------------------------------------------------------
# Guided scenarios: each preset loads the sidebar so the app tells its own story.
# Presets are applied BEFORE the sidebar widgets are built (Streamlit forbids
# writing a widget's value after it exists), using a pending-state in session.
# ---------------------------------------------------------------------------
SCENARIOS = {
    "😌 Calm market": {
        "preset": dict(k_half_spread=1, k_skew=0.3, k_with_informed=False,
                       k_p_buy=0.50, k_edge=1.0),
        "note": "Balanced noise, no informed traders. Your quotes harvest the "
                "spread and the P&L curve grinds steadily up. This is a "
                "market-maker's dream: pure liquidity provision.",
    },
    "🌊 One-sided flow": {
        "preset": dict(k_half_spread=1, k_skew=0.0, k_with_informed=False,
                       k_p_buy=0.62, k_edge=1.0),
        "note": "Persistent buying pressure and NO inventory skew (naive maker). "
                "Watch the inventory chart run away as you're forced to keep "
                "selling — spread capture looks fine while the position sinks you.",
    },
    "🦈 Adverse selection": {
        "preset": dict(k_half_spread=1, k_skew=0.3, k_with_informed=True,
                       k_p_buy=0.50, k_edge=0.5),
        "note": "An aggressive informed trader who sees the hidden true value and "
                "picks off your stale quotes. Check the 'caught in the act' fills "
                "and the negative informed markout — you're being selected.",
    },
    "🛡️ Defend by widening": {
        "preset": dict(k_half_spread=4, k_skew=0.4, k_with_informed=True,
                       k_p_buy=0.50, k_edge=0.5),
        "note": "Same toxic market as adverse selection, but now you quote WIDE "
                "and skew hard. Far fewer pick-offs, inventory stays tight, and the "
                "P&L recovers. This is the desk's response to toxic flow.",
    },
}

# Apply any pending preset before the sidebar is constructed.
if "_preset" in st.session_state:
    for key, value in st.session_state.pop("_preset").items():
        st.session_state[key] = value


# ---------------------------------------------------------------------------
# Sidebar — your dials (used by the Simulator view).
# ---------------------------------------------------------------------------
st.sidebar.header("Your quoting strategy")
half_spread = st.sidebar.slider("Half-spread (ticks from fair value)", 1, 6, 1,
    key="k_half_spread",
    help="How far your bid/ask sit from fair value. Wider = more edge per fill "
         "but fewer fills, and less adverse selection.")
quote_size = st.sidebar.slider("Quote size (units per side)", 1, 20, 5, key="k_quote_size")
skew = st.sidebar.slider("Inventory skew", 0.0, 1.5, 0.3, 0.1, key="k_skew",
    help="How hard you lean quotes against your position to get back to flat. "
         "0 = naive symmetric maker. Too high = you flatten so eagerly you kill "
         "your own spread edge.")
max_inventory = st.sidebar.slider("Inventory cap (hard risk limit)", 5, 100, 40, 5,
    key="k_max_inventory")
vol_coef = st.sidebar.slider("Widen-on-volatility", 0.0, 2.0, 0.5, 0.1, key="k_vol_coef")

st.sidebar.header("The market")
with_informed = st.sidebar.checkbox("Add an informed trader (adverse selection)",
    value=True, key="k_with_informed",
    help="An agent who sees the hidden true value and picks off your stale quotes. "
         "Turn off for a pure-noise market.")
edge = st.sidebar.slider("Informed trader's edge threshold", 0.0, 5.0, 1.0, 0.5,
    key="k_edge",
    help="How mispriced the book must be before the informed trader acts. Lower = "
         "more aggressive, more toxic flow.")
informed_size = st.sidebar.slider("Informed order size", 1, 20, 5, key="k_informed_size")
p_buy = st.sidebar.slider("Noise buy/sell bias", 0.30, 0.70, 0.50, 0.01, key="k_p_buy",
    help="0.50 = balanced noise. Push it away from 0.5 for one-sided pressure.")

st.sidebar.header("Run")
n_cycles = st.sidebar.slider("Cycles (length of the session)", 100, 2000, 500, 100,
    key="k_n_cycles")
seed = st.sidebar.number_input("Random seed", value=1, step=1, key="k_seed")


# ---------------------------------------------------------------------------
# Simulator view
# ---------------------------------------------------------------------------
def render_simulator():
    st.subheader("🎬 Guided scenarios")
    st.caption("New here? Click one to load a situation and see what to look for.")
    cols = st.columns(len(SCENARIOS))
    for col, (name, sc) in zip(cols, SCENARIOS.items()):
        if col.button(name, use_container_width=True):
            st.session_state["_preset"] = sc["preset"]
            st.session_state["_scenario_note"] = sc["note"]
            st.rerun()
    if "_scenario_note" in st.session_state:
        st.info(st.session_state["_scenario_note"])
    st.divider()

    res = simulate(n_cycles=n_cycles, half_spread=half_spread, quote_size=quote_size,
                   skew=skew, max_inventory=max_inventory, vol_coef=vol_coef,
                   with_informed=with_informed, p_buy=p_buy,
                   informed_size=informed_size, edge=edge, seed=int(seed))
    pnl = res["pnl"]

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total P&L", f"{pnl:+,.0f}", delta="profit" if pnl >= 0 else "loss",
              delta_color="normal" if pnl >= 0 else "inverse")
    c2.metric("Cash (captured spread)", f"{res['cash']:+,.0f}")
    c3.metric("Ending inventory", f"{res['inventory']:+d}")
    c4.metric("Max inventory carried", f"{res['max_abs_inventory']:d}",
              help="The most risk you held at any point. Small = disciplined.")
    c5.metric("Picked-off fills", f"{res['n_informed_fills']:d}",
              help="Fills the informed trader took against your stale quotes.")

    st.markdown(
        f"**Where the money came from & went:** you earned "
        f"**{res['markout_noise']:+,.0f}** of markout from *noise* flow and gave "
        f"back **{res['markout_informed']:+,.0f}** to *informed* flow. "
        f"Market-making is winning that tug-of-war."
    )
    st.divider()

    left, right = st.columns(2)
    with left:
        st.subheader("Price vs. the hidden true value")
        fig, ax = plt.subplots(figsize=(6, 3.2))
        ax.plot(res["tv_hist"], color=GREY, lw=1.4, label="true value (you can't see this)")
        ax.plot(res["mid_hist"], color=BLUE, lw=1.4, label="book mid (what you quote around)")
        ax.set_xlabel("cycle"); ax.set_ylabel("price")
        ax.legend(fontsize=8, loc="best"); ax.grid(alpha=0.2)
        st.pyplot(fig)
        st.caption("The mid chases the true value with a lag. That lag is the gap "
                   "the informed trader exploits.")
    with right:
        st.subheader("P&L over the session")
        fig, ax = plt.subplots(figsize=(6, 3.2))
        ax.plot(res["pnl_hist"], color=GREEN if pnl >= 0 else RED, lw=1.6)
        ax.axhline(0, color=GREY, lw=0.8)
        ax.set_xlabel("cycle"); ax.set_ylabel("P&L"); ax.grid(alpha=0.2)
        st.pyplot(fig)
        st.caption("Grinds up when noise dominates; bleeds when informed flow picks you off.")

    left2, right2 = st.columns(2)
    with left2:
        st.subheader("Inventory over time (your risk)")
        fig, ax = plt.subplots(figsize=(6, 3.2))
        ax.plot(res["inv_hist"], color=BLUE, lw=1.2)
        ax.axhline(0, color=GREY, lw=0.8)
        ax.axhline(max_inventory, color=RED, lw=0.8, ls="--", label="cap")
        ax.axhline(-max_inventory, color=RED, lw=0.8, ls="--")
        ax.fill_between(range(len(res["inv_hist"])), res["inv_hist"], 0, alpha=0.15, color=BLUE)
        ax.set_xlabel("cycle"); ax.set_ylabel("position"); ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
        st.pyplot(fig)
        st.caption("Skew and the cap should keep this hugging zero. Runaway inventory = danger.")
    with right2:
        st.subheader("Order book depth (final snapshot)")
        book = res["book"]
        bid_prices = sorted(book.bids)
        ask_prices = sorted(book.asks)
        fig, ax = plt.subplots(figsize=(6, 3.2))
        if bid_prices:
            ax.bar(bid_prices, [book.depth_at("bid", p) for p in bid_prices],
                   color=GREEN, width=0.8, label="bids")
        if ask_prices:
            ax.bar(ask_prices, [book.depth_at("ask", p) for p in ask_prices],
                   color=RED, width=0.8, label="asks")
        ax.set_xlabel("price"); ax.set_ylabel("resting quantity"); ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
        st.pyplot(fig)
        st.caption("Green = buyers, red = sellers. The gap between the tallest green "
                   "and shortest red is the spread. Uneven depth emerges on its own.")

    st.divider()
    if res["worst_pickoffs"]:
        st.subheader("🎯 Caught in the act — your worst pick-offs")
        st.caption("The informed trader took these fills against your stale quote, "
                   "right before the price caught up to true value.")
        for fill, tv, m in res["worst_pickoffs"]:
            act = "**sold**" if fill["side"] == "ask" else "**bought**"
            st.markdown(f"- You {act} {fill['qty']} @ {fill['price']} — but true "
                        f"value was **{tv:.1f}** → markout **{m:+.1f}**")


# ---------------------------------------------------------------------------
# Research view (Monte Carlo over many random markets)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _cached_sweep(n_seeds, n_cycles, edge, values):
    return sweep("half_spread", list(values), n_seeds=n_seeds, n_cycles=n_cycles,
                 with_informed=True, edge=edge, skew=0.3, p_buy=0.50)


@st.cache_data(show_spinner=False)
def _cached_tournament(n_seeds, n_cycles, edge):
    strategies = {
        "naive-tight":  dict(half_spread=1, skew=0.0),
        "naive-wide":   dict(half_spread=3, skew=0.0),
        "skewed-tight": dict(half_spread=1, skew=0.4),
        "skewed-wide":  dict(half_spread=3, skew=0.4),
        "balanced":     dict(half_spread=2, skew=0.3),
    }
    return tournament(strategies, n_seeds=n_seeds, n_cycles=n_cycles,
                      with_informed=True, edge=edge, p_buy=0.50)


def render_research():
    st.subheader("🔬 Monte Carlo research")
    st.caption("One run is mostly noise. Every result here is averaged over many "
               "random markets — the honest way to judge a strategy, and the "
               "antidote to overfitting to one lucky backtest.")

    rc1, rc2, rc3 = st.columns(3)
    n_seeds = rc1.slider("Markets per config (seeds)", 5, 40, 15, 5)
    r_cycles = rc2.slider("Cycles per run", 200, 1000, 500, 100)
    r_edge = rc3.slider("Market toxicity (lower = more informed flow)", 0.0, 3.0, 0.5, 0.5)

    with st.spinner("Running many markets..."):
        sweep_rows = _cached_sweep(n_seeds, r_cycles, r_edge, tuple(range(1, 7)))
        tour_rows = _cached_tournament(n_seeds, r_cycles, r_edge)

    st.markdown("#### Widen-to-defend: half-spread vs P&L")
    xs = [r["half_spread"] for r in sweep_rows]
    means = [r["mean_pnl"] for r in sweep_rows]
    stds = [r["std_pnl"] for r in sweep_rows]
    lo = [m - s for m, s in zip(means, stds)]
    hi = [m + s for m, s in zip(means, stds)]
    fig, ax = plt.subplots(figsize=(8, 3.4))
    ax.plot(xs, means, color=BLUE, lw=2, marker="o", label="mean P&L")
    ax.fill_between(xs, lo, hi, alpha=0.15, color=BLUE, label="±1 std")
    ax.axhline(0, color=GREY, lw=0.8)
    ax.set_xlabel("half-spread (ticks)"); ax.set_ylabel("P&L over the session")
    ax.legend(fontsize=8); ax.grid(alpha=0.2)
    st.pyplot(fig)
    st.caption("Against toxic flow, tight quoting is a reliable loser; widening cuts "
               "pick-offs and restores profit. The band is the spread across markets.")

    st.divider()
    st.markdown("#### Strategy tournament: P&L is not the objective — risk-adjusted return is")
    df = pd.DataFrame(tour_rows)[
        ["name", "mean_pnl", "std_pnl", "win_rate", "risk_adj", "mean_max_inv"]]
    df.columns = ["strategy", "mean P&L", "P&L std", "win rate",
                  "risk-adjusted", "avg max inventory"]

    fig, ax = plt.subplots(figsize=(8, 3.2))
    order = df.sort_values("mean P&L")
    colors = [GREEN if v >= 0 else RED for v in order["mean P&L"]]
    ax.barh(order["strategy"], order["mean P&L"], color=colors,
            xerr=order["P&L std"], capsize=4, alpha=0.85)
    ax.axvline(0, color=GREY, lw=0.8)
    ax.set_xlabel("mean P&L (±1 std)"); ax.grid(alpha=0.2, axis="x")
    st.pyplot(fig)

    st.dataframe(
        df.style.format({"mean P&L": "{:+.0f}", "P&L std": "{:.0f}",
                         "win rate": "{:.0%}", "risk-adjusted": "{:+.2f}",
                         "avg max inventory": "{:.1f}"}),
        use_container_width=True, hide_index=True)
    st.caption("The highest raw-P&L strategy usually isn't the one a desk would run: "
               "look at the risk-adjusted column and the inventory carried. Return "
               "PER unit of risk is what matters — max P&L is a rookie's scoreboard.")


# ---------------------------------------------------------------------------
# Learn view
# ---------------------------------------------------------------------------
def render_learn():
    st.subheader("🎓 The concepts, in plain English")
    st.caption("Everything the simulator demonstrates — the vocabulary of a "
               "trading desk. Pick one, or expand them all.")
    concept_map = dict(CONCEPTS)
    choice = st.selectbox("Pick a concept", list(concept_map))
    st.info(f"**{choice}** — {concept_map[choice]}")
    with st.expander("Show all concepts at once (the whole curriculum)"):
        for term, expl in CONCEPTS:
            st.markdown(f"**{term}** — {expl}")

    st.divider()
    st.subheader("🧠 Self-quiz")
    st.caption("Every one of these is fair game in an S&T interview. Answer them, "
               "then check yourself.")

    answers = []
    for i, item in enumerate(QUIZ):
        a = st.radio(f"**Q{i + 1}.** {item['q']}", item["options"],
                     index=None, key=f"quiz_{i}")
        answers.append(a)

    if st.button("Check my answers", type="primary"):
        score = 0
        for i, item in enumerate(QUIZ):
            correct = item["options"][item["answer"]]
            if answers[i] == correct:
                score += 1
                st.success(f"**Q{i + 1}: ✓ correct.** {item['why']}")
            else:
                picked = answers[i] if answers[i] is not None else "(no answer)"
                st.error(f"**Q{i + 1}: ✗** You picked *{picked}*. "
                         f"Correct: **{correct}**. {item['why']}")
        st.metric("Your score", f"{score} / {len(QUIZ)}")
        if score == len(QUIZ):
            st.balloons()


# ---------------------------------------------------------------------------
# Header + navigation
# ---------------------------------------------------------------------------
st.title("📈 Order Book + Market-Making Simulator")
st.caption("You're the market-maker. Quote both sides, capture the spread, and "
           "manage the inventory and adverse selection that decide whether you keep it. "
           "A self-contained sim — no real data, no money. A gym for microstructure intuition.")

view = st.segmented_control("View", ["🎮 Simulator", "🔬 Research", "🎓 Learn"],
                            default="🎮 Simulator", label_visibility="collapsed")

if view == "🔬 Research":
    render_research()
elif view == "🎓 Learn":
    render_learn()
else:
    render_simulator()
