"""
teach.py — Module 8 of the Order Book + Market-Making Simulator.

A rule-based teaching layer (no API key, free path): plain-English explanations of
the core microstructure concepts the simulator demonstrates, plus a self-quiz.

It serves two audiences:
  * a recruiter/visitor who opens the live app and wants the concepts explained, and
  * the builder, as interview self-prep -- every quiz answer is something a real
    S&T interview can ask.

The content is deliberately grounded in what the engine actually does, so the
lesson and the simulation reinforce each other.

Runnable standalone:  python teach.py   (prints the concepts and quizzes you in the terminal)
"""

# Ordered so it reads as a curriculum: structure -> trades -> making markets -> risk.
CONCEPTS = [
    ("Limit order book",
     "The record of every resting buy (bid) and sell (ask) order, organized by "
     "price level. Bids below, asks above, the spread in between. It's the "
     "foundation of every modern market."),

    ("Price-time priority",
     "The rule that decides who trades first: the best price wins, and among "
     "orders at the same price, the one that arrived earliest wins. In the code "
     "this falls out of the data structure -- a dict of price levels, each a "
     "first-in-first-out queue."),

    ("The spread",
     "Best ask minus best bid. It's the cost of immediacy for anyone who wants to "
     "trade right now -- and the raw material a market-maker tries to capture by "
     "quoting both sides."),

    ("Maker vs taker",
     "The resting order provides ('makes') liquidity; the incoming aggressive "
     "order removes ('takes') it. Trades print at the MAKER's price, so a taker "
     "who crosses the spread can get price improvement. Exchanges charge takers "
     "and rebate makers."),

    ("Market-making P&L",
     "Total P&L = cash (from trades) + inventory x fair value (mark-to-market). "
     "With flat inventory, cash is the captured spread -- pure profit. The catch "
     "is the inventory term: you can capture spread all day and still lose on the "
     "position you were forced to hold."),

    ("Inventory risk",
     "Every fill changes your position. One-sided flow forces you to accumulate "
     "inventory you never wanted, turning a market-maker into an accidental "
     "directional trader. Managing it -- not capturing the spread -- is the hard "
     "part of the job."),

    ("Inventory skew",
     "The defense against inventory risk: quote around a reservation price that "
     "leans against your position (short -> quote higher to buy back; long -> "
     "quote lower to sell). You actively steer toward flat instead of piling on."),

    ("Adverse selection",
     "Getting picked off by someone who knows more than you. An informed trader "
     "only trades when your quote is stale -- lifting your too-cheap offer right "
     "before the price rises. Your fills become systematically the ones you'd "
     "rather not have done."),

    ("Markout",
     "How you measure adverse selection: compare each fill's price to the true "
     "value a moment later. Positive markout means you traded well; consistently "
     "negative markout means you're being picked off. Real desks watch it closely."),

    ("Widening the spread",
     "The response to toxic (informed-heavy) flow: quote further from fair value. "
     "You take fewer pick-offs, but quote too wide and the harmless noise traders "
     "skip you too, so you stop earning. Finding that balance is the job."),

    ("Risk-adjusted return",
     "Return per unit of risk (mean P&L / its volatility -- a Sharpe-like ratio). "
     "A desk doesn't want the strategy with the biggest P&L; it wants the best "
     "return for the risk carried. Max P&L is a rookie's scoreboard."),

    ("Zero-intelligence flow",
     "A model where order flow is purely random -- no strategy, no view. The "
     "striking result is that even random posting and cancelling produces a "
     "realistic book with a spread and a random-walk price. It shows how much of "
     "market structure is mechanical rather than informed."),
]


QUIZ = [
    {"q": "Two limit buy orders rest at the same price. Which one fills first?",
     "options": ["The larger one", "The one that arrived first",
                 "The smaller one", "Whichever is chosen at random"],
     "answer": 1,
     "why": "Price-time priority: same price, so the earlier arrival (front of the "
            "FIFO queue) trades first."},

    {"q": "You send a limit buy at 105 and the best ask resting is 101. At what "
          "price do you trade?",
     "options": ["105 (your price)", "103 (the midpoint)",
                 "101 (the maker's price)", "No trade -- it rests at 105"],
     "answer": 2,
     "why": "Trades print at the MAKER's (resting) price. You cross and get price "
            "improvement, buying at 101 instead of your limit of 105."},

    {"q": "A market-maker's cash shows +21,000 in captured spread but total P&L is "
          "-5,000. What most likely happened?",
     "options": ["A calculation bug",
                 "It accumulated a large inventory that moved against it",
                 "It paid too much in fees",
                 "The spread was negative"],
     "answer": 1,
     "why": "Total P&L = cash + inventory x fair value. Spread capture is real, but "
            "a big adverse inventory position (mark-to-market) can more than wipe "
            "it out. Inventory is the risk, not the spread."},

    {"q": "You're a market-maker who has become very SHORT. How should you skew "
          "your quotes?",
     "options": ["Lower both quotes", "Raise both quotes",
                 "Widen symmetrically", "Stop quoting entirely"],
     "answer": 1,
     "why": "Raise both quotes: a higher bid makes you more likely to buy back "
            "(reduce the short), and a higher ask makes you less likely to sell "
            "more. You lean against your inventory toward flat."},

    {"q": "An informed trader tends to trade against you right before the price "
          "moves in their favor. This is called:",
     "options": ["Slippage", "Adverse selection",
                 "Front-running", "Market impact"],
     "answer": 1,
     "why": "Adverse selection: your counterparty has information, so your fills "
            "are systematically on the losing side. Markout measures it."},

    {"q": "Your flow is getting more toxic (more informed traders). What's the "
          "standard defensive response?",
     "options": ["Quote tighter to win more flow", "Widen your spread",
                 "Increase your quote size", "Ignore it and capture more spread"],
     "answer": 1,
     "why": "Widen. A wider spread means informed traders need more mispricing to "
            "pick you off, so fewer do. The cost is that some noise flow skips you."},

    {"q": "Strategy A averages +149 P&L with high volatility and a large inventory; "
          "Strategy B averages +87 with low volatility and small inventory. Which "
          "would a desk more likely run?",
     "options": ["A -- higher P&L always wins",
                 "B -- better return per unit of risk",
                 "Neither -- both are unprofitable",
                 "Whichever had the better single best day"],
     "answer": 1,
     "why": "Desks optimize risk-adjusted return, not raw P&L. B's higher return "
            "per unit of risk and smaller inventory make it the safer, preferred "
            "book despite the lower headline number."},

    {"q": "In the simulator, most order-flow events are NOT trades. What are they?",
     "options": ["Errors", "Limit orders posting and cancels pulling them",
                 "Market data updates", "Settlement instructions"],
     "answer": 1,
     "why": "Real flow is dominated by resting limit orders and cancellations -- "
            "quotes flicker constantly, and most orders are cancelled, not filled."},
]


def _run_terminal_quiz():
    print("\n=== Microstructure concepts ===")
    for term, expl in CONCEPTS:
        print(f"\n* {term}\n    {expl}")

    print("\n\n=== Self-quiz ===")
    score = 0
    for i, item in enumerate(QUIZ, 1):
        print(f"\nQ{i}. {item['q']}")
        for j, opt in enumerate(item["options"]):
            print(f"   {chr(97 + j)}) {opt}")
        correct = item["options"][item["answer"]]
        print(f"   -> Answer: {correct}")
        print(f"      Why: {item['why']}")
        score += 1
    print(f"\n({len(QUIZ)} questions -- run the app's Learn tab to answer them interactively.)")


if __name__ == "__main__":
    _run_terminal_quiz()
