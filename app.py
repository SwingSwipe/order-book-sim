"""
app.py — Module 6 of the Order Book + Market-Making Simulator.

The visualization cockpit. You set the market-maker's parameters and the market's
toxicity, run the simulation, and SEE what the earlier modules only printed:
the order book depth, your P&L curve, your inventory over time, the price vs the
(hidden) true value, and where your money came from and went.

Engine/UI split: all logic lives in the engine modules; this file only draws.

Run:  python -m streamlit run app.py     (or the preview server, port 8503)
"""

import matplotlib.pyplot as plt
import streamlit as st

from informed import simulate

st.set_page_config(page_title="Order Book + Market-Making Sim", layout="wide")

GREEN, RED, BLUE, GREY = "#16a34a", "#dc2626", "#2563eb", "#9ca3af"


# ---------------------------------------------------------------------------
# Sidebar — you are the desk. These are your dials.
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
# Header
# ---------------------------------------------------------------------------
st.title("📈 Order Book + Market-Making Simulator")
st.caption("You're the market-maker. Quote both sides, capture the spread, and "
           "manage the inventory and adverse selection that decide whether you keep it. "
           "A self-contained sim — no real data, no money. A gym for microstructure intuition.")

res = simulate(n_cycles=n_cycles, half_spread=half_spread, quote_size=quote_size,
               skew=skew, max_inventory=max_inventory, vol_coef=vol_coef,
               with_informed=with_informed, p_buy=p_buy, informed_size=informed_size,
               edge=edge, seed=int(seed))


# ---------------------------------------------------------------------------
# Headline metrics
# ---------------------------------------------------------------------------
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
    f"**Where the money came from & went:** you earned **{res['markout_noise']:+,.0f}** "
    f"of markout from *noise* flow and gave back **{res['markout_informed']:+,.0f}** "
    f"to *informed* flow. Market-making is winning that tug-of-war."
)

st.divider()

# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
left, right = st.columns(2)

# --- Price vs hidden true value ---
with left:
    st.subheader("Price vs. the hidden true value")
    fig, ax = plt.subplots(figsize=(6, 3.2))
    mids = [m for m in res["mid_hist"] if m is not None]
    ax.plot(res["tv_hist"], color=GREY, lw=1.4, label="true value (you can't see this)")
    ax.plot(res["mid_hist"], color=BLUE, lw=1.4, label="book mid (what you quote around)")
    ax.set_xlabel("cycle"); ax.set_ylabel("price")
    ax.legend(fontsize=8, loc="best"); ax.grid(alpha=0.2)
    st.pyplot(fig)
    st.caption("The mid chases the true value with a lag. That lag is the gap the "
               "informed trader exploits.")

# --- P&L curve ---
with right:
    st.subheader("P&L over the session")
    fig, ax = plt.subplots(figsize=(6, 3.2))
    ax.plot(res["pnl_hist"], color=GREEN if pnl >= 0 else RED, lw=1.6)
    ax.axhline(0, color=GREY, lw=0.8)
    ax.set_xlabel("cycle"); ax.set_ylabel("P&L"); ax.grid(alpha=0.2)
    st.pyplot(fig)
    st.caption("Grinds up when noise dominates; bleeds when informed flow picks you off.")

left2, right2 = st.columns(2)

# --- Inventory over time ---
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

# --- Order book depth snapshot ---
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
    st.caption("Green = buyers, red = sellers. The gap between the tallest green and "
               "shortest red is the spread. Uneven depth emerges on its own.")

st.divider()

# --- Caught in the act ---
if res["worst_pickoffs"]:
    st.subheader("🎯 Caught in the act — your worst pick-offs")
    st.caption("The informed trader took these fills against your stale quote, right "
               "before the price caught up to true value.")
    for fill, tv, m in res["worst_pickoffs"]:
        act = "**sold**" if fill["side"] == "ask" else "**bought**"
        st.markdown(f"- You {act} {fill['qty']} @ {fill['price']} — but true value "
                    f"was **{tv:.1f}** → markout **{m:+.1f}**")

with st.expander("📖 How to read this / what you're looking at"):
    st.markdown(
        "- **A market-maker makes money from noise and loses it to information.** "
        "Your job is to win that tug-of-war.\n"
        "- **Inventory is the risk, not the spread.** Watch the inventory chart: if it "
        "runs away, one price move wipes out a session of spread capture.\n"
        "- **Widen to defend.** Raise the half-spread against toxic (informed) flow — "
        "you'll take fewer pick-offs, but quote too wide and noise skips you too.\n"
        "- Try: turn the informed trader **off** and watch P&L grind smoothly up. Turn it "
        "**on** with a low edge threshold and watch it bleed. Then widen your spread to fight back."
    )
