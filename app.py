"""
app.py — Modules 6 & 8 of the Order Book + Market-Making Simulator.

Two views:
  * Simulator (Module 6): set the market-maker's parameters and the market's
    toxicity, run the sim, and SEE the book depth, P&L, inventory, price vs the
    hidden true value, and where the money came from and went.
  * Learn (Module 8): rule-based explanations of the core microstructure concepts
    plus an interactive self-quiz.

Engine/UI split: all logic lives in the engine modules; this file only draws.

Run:  python -m streamlit run app.py     (or the preview server, port 8504)
"""

import matplotlib.pyplot as plt
import streamlit as st

from informed import simulate
from teach import CONCEPTS, QUIZ

st.set_page_config(page_title="Order Book + Market-Making Sim", layout="wide")

GREEN, RED, BLUE, GREY = "#16a34a", "#dc2626", "#2563eb", "#9ca3af"


# ---------------------------------------------------------------------------
# Sidebar — you are the desk. These are your dials (used by the Simulator view).
# ---------------------------------------------------------------------------
st.sidebar.header("Your quoting strategy")
half_spread = st.sidebar.slider("Half-spread (ticks from fair value)", 1, 6, 1,
    help="How far your bid/ask sit from fair value. Wider = more edge per fill "
         "but fewer fills, and less adverse selection.")
quote_size = st.sidebar.slider("Quote size (units per side)", 1, 20, 5)
skew = st.sidebar.slider("Inventory skew", 0.0, 1.5, 0.3, 0.1,
    help="How hard you lean quotes against your position to get back to flat. "
         "0 = naive symmetric maker. Too high = you flatten so eagerly you kill "
         "your own spread edge.")
max_inventory = st.sidebar.slider("Inventory cap (hard risk limit)", 5, 100, 40, 5)
vol_coef = st.sidebar.slider("Widen-on-volatility", 0.0, 2.0, 0.5, 0.1)

st.sidebar.header("The market")
with_informed = st.sidebar.checkbox("Add an informed trader (adverse selection)",
    value=True, help="An agent who sees the hidden true value and picks off your "
                     "stale quotes. Turn off for a pure-noise market.")
edge = st.sidebar.slider("Informed trader's edge threshold", 0.0, 5.0, 1.0, 0.5,
    help="How mispriced the book must be before the informed trader acts. Lower = "
         "more aggressive, more toxic flow.")
informed_size = st.sidebar.slider("Informed order size", 1, 20, 5)
p_buy = st.sidebar.slider("Noise buy/sell bias", 0.30, 0.70, 0.50, 0.01,
    help="0.50 = balanced noise. Push it away from 0.5 for one-sided pressure.")

st.sidebar.header("Run")
n_cycles = st.sidebar.slider("Cycles (length of the session)", 100, 2000, 500, 100)
seed = st.sidebar.number_input("Random seed", value=1, step=1)


# ---------------------------------------------------------------------------
# Simulator view (Module 6)
# ---------------------------------------------------------------------------
def render_simulator():
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

    with st.expander("📖 How to read this / what you're looking at"):
        st.markdown(
            "- **A market-maker makes money from noise and loses it to information.** "
            "Your job is to win that tug-of-war.\n"
            "- **Inventory is the risk, not the spread.** Watch the inventory chart: "
            "if it runs away, one price move wipes out a session of spread capture.\n"
            "- **Widen to defend.** Raise the half-spread against toxic (informed) "
            "flow — fewer pick-offs, but quote too wide and noise skips you too.\n"
            "- Try: turn the informed trader **off** and watch P&L grind smoothly up. "
            "Turn it **on** with a low edge threshold and watch it bleed. Then widen "
            "your spread to fight back."
        )


# ---------------------------------------------------------------------------
# Learn view (Module 8)
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

view = st.segmented_control("View", ["🎮 Simulator", "🎓 Learn"],
                            default="🎮 Simulator", label_visibility="collapsed")

if view == "🎓 Learn":
    render_learn()
else:
    render_simulator()
