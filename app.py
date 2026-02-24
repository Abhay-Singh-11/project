import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import requests
import math

# =================================
# 🎨 Color helper (PCR INCLUDED now)
# =================================
def color_signal(label, text):
    if "Bullish" in text:
        st.markdown(f"**{label}:** :green[{text}]")
    elif "Bearish" in text:
        st.markdown(f"**{label}:** :red[{text}]")
    else:
        st.markdown(f"**{label}:** :orange[{text}]")


# =================================
# 🔴 Live PCR Fetch
# =================================
@st.cache_data(ttl=60)
def get_live_nifty_pcr():
    url = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=10)

        response = session.get(url, headers=headers, timeout=10)
        data = response.json()

        records = data["records"]["data"]

        put_oi = 0
        call_oi = 0

        for item in records:
            if "PE" in item:
                put_oi += item["PE"]["openInterest"]
            if "CE" in item:
                call_oi += item["CE"]["openInterest"]

        if call_oi == 0:
            return None

        return round(put_oi / call_oi, 3)

    except Exception:
        return None


# =================================
# 🧠 Scoring Function
# =================================
def calculate_score(
    nifty_up,
    nifty_down,
    pcr,
    advances,
    declines,
    sector_bullish,
    sector_bearish,
):
    score = 0
    details = {}

    # Rule 1: Nifty Top 10 (30)
    if nifty_up >= 6:
        score_nifty = (nifty_up / 10) * 30
        details["Nifty"] = f"{score_nifty:.1f} Bullish"
    elif nifty_down >= 6:
        score_nifty = (nifty_down / 10) * 30
        details["Nifty"] = f"{score_nifty:.1f} Bearish"
    else:
        score_nifty = 15
        details["Nifty"] = "15 Neutral"
    score += score_nifty

    # Rule 2: PCR (30)
    if pcr > 1:
        score_pcr = min(30, (pcr - 1) * 30 + 15)
        details["PCR"] = f"{score_pcr:.1f} Bullish"
    elif pcr < 0.7:
        score_pcr = min(30, (1 - pcr) * 30 + 15)
        details["PCR"] = f"{score_pcr:.1f} Bearish"
    else:
        score_pcr = 15
        details["PCR"] = "15 Neutral"
    score += score_pcr

    # Rule 3: Advance–Decline (nonlinear)
    if advances > 0 and declines > 0:
        ratio = advances / declines
        strength = min(1, abs(math.log(ratio)))
        score_adv = strength * 20

        if ratio > 1.1:
            details["Advance-Decline"] = f"{score_adv:.1f} Bullish"
        elif ratio < 0.9:
            details["Advance-Decline"] = f"{score_adv:.1f} Bearish"
        else:
            score_adv = 10
            details["Advance-Decline"] = "10 Neutral"
    else:
        score_adv = 10
        details["Advance-Decline"] = "10 Neutral"

    score += score_adv

    # Rule 4: Sector Heatmap (nonlinear)
    if sector_bullish > 0 and sector_bearish > 0:
        ratio = sector_bullish / sector_bearish
        strength = min(1, abs(math.log(ratio)))
        score_sector = strength * 20

        if ratio > 1.1:
            details["Sector"] = f"{score_sector:.1f} Bullish"
        elif ratio < 0.9:
            details["Sector"] = f"{score_sector:.1f} Bearish"
        else:
            score_sector = 10
            details["Sector"] = "10 Neutral"
    else:
        score_sector = 10
        details["Sector"] = "10 Neutral"

    score += score_sector

    return score, details


# =================================
# 🎯 Trade Engine
# =================================
def get_trade_recommendation(score, details):
    bullish_count = sum("Bullish" in v for v in details.values())
    bearish_count = sum("Bearish" in v for v in details.values())

    signal_gap = abs(bullish_count - bearish_count)

    if signal_gap <= 1:
        return {
            "type": "FLAT",
            "message": "⚖️ Signals not aligned → Sell BOTH sides",
            "delta": "10–20Δ both CE & PE",
        }

    if score < 65:
        return {
            "type": "FLAT",
            "message": "🟡 Low conviction → Prefer selling both sides",
            "delta": "10–20Δ both CE & PE",
        }

    direction = "PUT side (bullish)" if bullish_count > bearish_count else "CALL side (bearish)"

    if score >= 80:
        return {
            "type": "DIRECTIONAL",
            "message": f"🔥 Strong edge → Sell {direction}",
            "delta": "0.30–0.40Δ",
        }

    return {
        "type": "DIRECTIONAL",
        "message": f"✅ Decent edge → Sell {direction}",
        "delta": "0.30Δ",
    }


# =================================
# 🎨 UI
# =================================
st.set_page_config(page_title="Option Selling Dashboard", layout="wide")
st.title("📊 Option Selling Sentiment Dashboard")

st.header("Input Your Signals")

# -------- PCR --------
st.subheader("PCR Source")
use_live_pcr = st.toggle("Use Live NIFTY PCR", value=True)

if use_live_pcr:
    live_pcr = get_live_nifty_pcr()

    if live_pcr is not None:
        st.metric("Live NIFTY PCR", live_pcr)
        pcr = live_pcr
    else:
        st.warning("Live PCR unavailable — enter manually")
        pcr = st.number_input("PCR Ratio (Manual)", min_value=0.0, step=0.01)
else:
    pcr = st.number_input("PCR Ratio (Manual)", min_value=0.0, step=0.01)

# -------- Nifty Breadth --------
st.subheader("📊 Nifty Top 10 Breadth")
col1, col2 = st.columns(2)

with col1:
    nifty_up = st.number_input("🟢 Nifty Top 10 Up Stocks", 0, 10)
with col2:
    nifty_down = st.number_input("🔴 Nifty Top 10 Down Stocks", 0, 10)

# -------- Advance Decline --------
st.subheader("📈 Market Breadth (Advance–Decline)")
col3, col4 = st.columns(2)

with col3:
    advances = st.number_input("🟢 Advances", min_value=0)
with col4:
    declines = st.number_input("🔴 Declines", min_value=0)

# -------- Sector --------
st.subheader("🏭 Sector Heatmap")
col5, col6 = st.columns(2)

with col5:
    sector_bullish = st.number_input("🟢 Bullish Sectors", 0, 12)
with col6:
    sector_bearish = st.number_input("🔴 Bearish Sectors", 0, 12)

if "history" not in st.session_state:
    st.session_state.history = []

# =================================
# 🚀 Calculate
# =================================
if st.button("Calculate Sentiment Score"):
    score, details = calculate_score(
        nifty_up,
        nifty_down,
        pcr,
        advances,
        declines,
        sector_bullish,
        sector_bearish,
    )

    st.subheader("📌 Rule Breakdown")
    for k, v in details.items():
        color_signal(k, v)

    # -------- Score color --------
    if score >= 70:
        st.markdown(f"## 🟢 Overall Sentiment Score: **{score:.1f}/100**")
    elif score <= 40:
        st.markdown(f"## 🔴 Overall Sentiment Score: **{score:.1f}/100**")
    else:
        st.markdown(f"## 🟡 Overall Sentiment Score: **{score:.1f}/100**")

    # -------- Trade --------
    st.subheader("🎯 Trade Recommendation")
    trade = get_trade_recommendation(score, details)

    if trade["type"] == "DIRECTIONAL":
        st.success(trade["message"])
    else:
        st.warning(trade["message"])

    st.write(f"**Suggested Delta:** {trade['delta']}")

    # -------- Pie --------
    st.subheader("📈 Advance vs Decline Chart")
    fig, ax = plt.subplots()
    ax.pie(
        [advances, declines],
        labels=["Advances", "Declines"],
        autopct="%1.1f%%",
        colors=["green", "red"],
    )
    st.pyplot(fig)
    plt.close(fig)

    # -------- History --------
    st.session_state.history.append(
        {
            "Score": score,
            "Trade": trade["message"],
            "Delta": trade["delta"],
        }
    )

# =================================
# 📜 History
# =================================
if st.session_state.history:
    st.header("📜 Trade History")
    df = pd.DataFrame(st.session_state.history)
    st.dataframe(df)