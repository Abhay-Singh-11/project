
def trading_signal(nifty_direction, pcr, adv_dec, sector_direction):
    signals = []

    # Rule 1: Nifty Top 10
    signals.append(nifty_direction)

    # Rule 2: PCR
    if pcr > 1:
        signals.append("Bullish")
    elif pcr < 0.7:
        signals.append("Bearish")
    else:
        signals.append("Neutral")

    # Rule 3: Advance-Decline
    if adv_dec["advances"] > adv_dec["declines"]:
        signals.append("Bullish")
    elif adv_dec["advances"] < adv_dec["declines"]:
        signals.append("Bearish")
    else:
        signals.append("Neutral")

    # Rule 4: Sector Heatmap
    signals.append(sector_direction)

    # Final Decision
    bullish_count = signals.count("Bullish")
    bearish_count = signals.count("Bearish")

    if bullish_count > bearish_count:
        return "Trade Suggestion: Bullish → Sell Puts (Bull Put Spread)"
    elif bearish_count > bullish_count:
        return "Trade Suggestion: Bearish → Sell Calls (Bear Call Spread)"
    else:
        return "Trade Suggestion: Neutral → Iron Condor / Short Straddle"

# Example usage
adv_dec_data = {"advances": 30, "declines": 20}
def trading_signal(nifty_direction, pcr, adv_dec, sector_direction):
    signals = []

    # Rule 1: Nifty Top 10
    signals.append(nifty_direction)

    # Rule 2: PCR
    if pcr > 1:
        signals.append("Bullish")
    elif pcr < 0.7:
        signals.append("Bearish")
    else:
        signals.append("Neutral")

    # Rule 3: Advance-Decline
    if adv_dec["advances"] > adv_dec["declines"]:
        signals.append("Bullish")
    elif adv_dec["advances"] < adv_dec["declines"]:
        signals.append("Bearish")
    else:
        signals.append("Neutral")

    # Rule 4: Sector Heatmap
    signals.append(sector_direction)

    # Final Decision
    bullish_count = signals.count("Bullish")
    bearish_count = signals.count("Bearish")

    if bullish_count > bearish_count:
        return "Trade Suggestion: Bullish → Sell Puts (Bull Put Spread)"
    elif bearish_count > bullish_count:
        return "Trade Suggestion: Bearish → Sell Calls (Bear Call Spread)"
    else:
        return "Trade Suggestion: Neutral → Iron Condor / Short Straddle"

# Example usage
adv_dec_data = {"advances": 30, "declines": 20}
print(trading_signal("Bullish", 0.85, adv_dec_data, "Neutral"))