import streamlit as st
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import math
from datetime import datetime
import pytz

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
NIFTY_TOP10 = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
    "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS"
]

SECTOR_INDICES = {
    "IT":       "^CNXIT",
    "Bank":     "^NSEBANK",
    "Auto":     "^CNXAUTO",
    "Pharma":   "^CNXPHARMA",
    "FMCG":     "^CNXFMCG",
    "Metal":    "^CNXMETAL",
    "Realty":   "^CNXREALTY",
    "Energy":   "^CNXENERGY",
    "Infra":    "^CNXINFRA",
    "Media":    "^CNXMEDIA",
}

IST = pytz.timezone("Asia/Kolkata")

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def ist_now():
    return datetime.now(IST)

def market_open():
    now = ist_now()
    if now.weekday() >= 5:
        return False
    t = now.time()
    return datetime.strptime("09:30", "%H:%M").time() <= t <= datetime.strptime("15:20", "%H:%M").time()

def time_warning():
    now = ist_now()
    t = now.time()
    open_t  = datetime.strptime("09:15", "%H:%M").time()
    safe_t  = datetime.strptime("09:30", "%H:%M").time()
    close_t = datetime.strptime("15:20", "%H:%M").time()
    hard_t  = datetime.strptime("15:30", "%H:%M").time()

    if t < open_t:
        return "pre", "⏳ Market not yet open. Data shown is from previous close."
    if open_t <= t < safe_t:
        return "warn", "⚠️ First 15 minutes — price discovery in progress. Avoid entering trades now."
    if close_t <= t < hard_t:
        return "danger", "🚨 After 3:20 PM — square off all positions! Do NOT enter new trades."
    if t >= hard_t:
        return "closed", "🔒 Market closed."
    return "ok", ""

def color_signal(label, text):
    if "Bullish" in text:
        st.markdown(f"**{label}:** :green[{text}]")
    elif "Bearish" in text:
        st.markdown(f"**{label}:** :red[{text}]")
    else:
        st.markdown(f"**{label}:** :orange[{text}]")

# ─────────────────────────────────────────────
# DATA FETCHERS  (all cached 5 min)
# ─────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def fetch_vix():
    try:
        ticker = yf.Ticker("^INDIAVIX")
        data = ticker.history(period="1d", interval="1m")
        if data.empty:
            return None
        return round(float(data["Close"].iloc[-1]), 2)
    except Exception:
        return None

@st.cache_data(ttl=300, show_spinner=False)
def fetch_nifty_top10():
    results = {}
    try:
        data = yf.download(
            NIFTY_TOP10,
            period="2d",
            interval="1d",
            progress=False,
            auto_adjust=True,
        )["Close"]

        for ticker in NIFTY_TOP10:
            name = ticker.replace(".NS", "")
            try:
                prev  = float(data[ticker].iloc[-2])
                today = float(data[ticker].iloc[-1])
                chg   = ((today - prev) / prev) * 100
                results[name] = round(chg, 2)
            except Exception:
                results[name] = None
    except Exception:
        pass
    return results

@st.cache_data(ttl=300, show_spinner=False)
def fetch_sectors():
    results = {}
    try:
        tickers = list(SECTOR_INDICES.values())
        data = yf.download(
            tickers,
            period="2d",
            interval="1d",
            progress=False,
            auto_adjust=True,
        )["Close"]

        for sector, sym in SECTOR_INDICES.items():
            try:
                prev  = float(data[sym].iloc[-2])
                today = float(data[sym].iloc[-1])
                chg   = ((today - prev) / prev) * 100
                results[sector] = round(chg, 2)
            except Exception:
                results[sector] = None
    except Exception:
        pass
    return results

@st.cache_data(ttl=300, show_spinner=False)
def fetch_oi_ratio():
    """
    OI Ratio = Total Put OI / Total Call OI from Nifty options chain.
    Acts as a PCR proxy. Returns (ratio, put_oi, call_oi) or None.
    """
    try:
        nifty = yf.Ticker("^NSEI")
        spot  = nifty.history(period="1d", interval="1m")
        if spot.empty:
            return None

        current_price = float(spot["Close"].iloc[-1])
        expirations   = nifty.options  # tuple of expiry date strings

        if not expirations:
            return None

        # Use nearest expiry
        nearest_expiry = expirations[0]
        chain = nifty.option_chain(nearest_expiry)

        put_oi  = int(chain.puts["openInterest"].sum())
        call_oi = int(chain.calls["openInterest"].sum())

        if call_oi == 0:
            return None

        ratio = round(put_oi / call_oi, 3)
        return ratio, put_oi, call_oi, nearest_expiry, round(current_price, 2)
    except Exception:
        return None

# ─────────────────────────────────────────────
# SCORING ENGINE
# ─────────────────────────────────────────────
def score_vix(vix):
    """Returns (adjustment, label). VIX is a filter, not a score contributor."""
    if vix is None:
        return 0, "Unknown"
    if vix > 20:
        return -999, f"{vix} 🔴 DANGER — Avoid selling"
    if vix > 15:
        return -10, f"{vix} 🟡 Elevated — Reduce size"
    return 0, f"{vix} 🟢 Safe zone"

def score_nifty_breadth(stock_changes):
    up   = sum(1 for v in stock_changes.values() if v is not None and v > 0)
    down = sum(1 for v in stock_changes.values() if v is not None and v < 0)
    total = up + down

    if total == 0:
        return 15, "15 Neutral", up, down

    if up >= 6:
        pts = round((up / 10) * 30, 1)
        return pts, f"{pts} Bullish ({up}/10 up)", up, down
    elif down >= 6:
        pts = round((down / 10) * 30, 1)
        return pts, f"{pts} Bearish ({down}/10 down)", up, down
    else:
        return 15, f"15 Neutral ({up} up / {down} down)", up, down

def score_oi_ratio(ratio):
    if ratio is None:
        return 15, "15 Neutral (data unavailable)"
    if ratio > 1:
        pts = round(min(30, (ratio - 1) * 30 + 15), 1)
        return pts, f"{pts} Bullish (OI ratio {ratio})"
    elif ratio < 0.7:
        pts = round(min(30, (1 - ratio) * 30 + 15), 1)
        return pts, f"{pts} Bearish (OI ratio {ratio})"
    else:
        return 15, f"15 Neutral (OI ratio {ratio})"

def score_adv_dec(advances, declines):
    if advances == 0 and declines == 0:
        return 10, "10 Neutral"
    if declines == 0:
        return 20, "20 Bullish (all advances)"
    if advances == 0:
        return 20, "20 Bearish (all declines)"
    ratio = advances / declines
    strength = min(1, abs(math.log(ratio)))
    pts = round(strength * 20, 1)
    if ratio > 1.1:
        return pts, f"{pts} Bullish ({advances}A / {declines}D)"
    elif ratio < 0.9:
        return pts, f"{pts} Bearish ({advances}A / {declines}D)"
    else:
        return 10, f"10 Neutral ({advances}A / {declines}D)"

def score_sectors(sector_changes):
    bull = sum(1 for v in sector_changes.values() if v is not None and v > 0)
    bear = sum(1 for v in sector_changes.values() if v is not None and v < 0)

    if bull == 0 and bear == 0:
        return 10, "10 Neutral", bull, bear

    if bull > 0 and bear > 0:
        ratio = bull / bear
        strength = min(1, abs(math.log(ratio)))
        pts = round(strength * 20, 1)
        if ratio > 1.1:
            return pts, f"{pts} Bullish ({bull} green / {bear} red)", bull, bear
        elif ratio < 0.9:
            return pts, f"{pts} Bearish ({bull} green / {bear} red)", bull, bear
        else:
            return 10, f"10 Neutral ({bull} green / {bear} red)", bull, bear
    elif bull > bear:
        return 20, f"20 Bullish ({bull} green / {bear} red)", bull, bear
    else:
        return 20, f"20 Bearish ({bull} green / {bear} red)", bull, bear

def get_trade_recommendation(score, details, vix_blocked):
    if vix_blocked:
        return {
            "type": "BLOCKED",
            "message": "🚫 VIX too high — Do NOT sell options today",
            "delta": "Stay flat",
        }

    bullish_count = sum("Bullish" in v for v in details.values())
    bearish_count = sum("Bearish" in v for v in details.values())
    signal_gap = abs(bullish_count - bearish_count)

    if signal_gap <= 1 or score < 65:
        return {
            "type": "FLAT",
            "message": "⚖️ Mixed signals → Sell BOTH sides (Iron Condor / Strangle)",
            "delta": "10–20Δ CE & PE",
        }

    direction = "PUT side (Bullish)" if bullish_count > bearish_count else "CALL side (Bearish)"

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

# ─────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Option Selling Dashboard",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Intraday Option Selling Dashboard")
st.caption(f"🕐 IST: {ist_now().strftime('%d %b %Y  %H:%M:%S')}  |  Data auto-refreshes every 5 min")

# ── Time warning banner ──
t_status, t_msg = time_warning()
if t_status == "ok":
    pass
elif t_status in ("danger", "closed"):
    st.error(t_msg)
elif t_status == "warn":
    st.warning(t_msg)
elif t_status == "pre":
    st.info(t_msg)

st.divider()

# ─────────────────────────────────────────────
# FETCH ALL DATA
# ─────────────────────────────────────────────
with st.spinner("⏳ Fetching live market data..."):
    vix          = fetch_vix()
    top10        = fetch_nifty_top10()
    sectors      = fetch_sectors()
    oi_data      = fetch_oi_ratio()

# OI ratio unpack
if oi_data:
    oi_ratio, put_oi, call_oi, expiry_date, nifty_spot = oi_data
else:
    oi_ratio = None
    put_oi = call_oi = 0
    expiry_date = "N/A"
    nifty_spot = None

# ─────────────────────────────────────────────
# LIVE DATA DISPLAY
# ─────────────────────────────────────────────
st.subheader("📡 Live Auto-Fetched Data")

c1, c2, c3, c4 = st.columns(4)

with c1:
    if vix:
        color = "normal" if vix < 15 else ("off" if vix < 20 else "inverse")
        st.metric("🌡️ India VIX", vix,
                  delta="Safe" if vix < 15 else ("Elevated" if vix < 20 else "DANGER"),
                  delta_color=color)
    else:
        st.metric("🌡️ India VIX", "Unavailable")

with c2:
    up_count   = sum(1 for v in top10.values() if v and v > 0)
    down_count = sum(1 for v in top10.values() if v and v < 0)
    st.metric("📊 Nifty Top 10", f"{up_count} up / {down_count} down")

with c3:
    if oi_ratio:
        st.metric("📈 OI Ratio (P/C)", oi_ratio,
                  delta="Bullish" if oi_ratio > 1 else ("Bearish" if oi_ratio < 0.7 else "Neutral"),
                  delta_color="normal" if oi_ratio > 1 else ("inverse" if oi_ratio < 0.7 else "off"))
        st.caption(f"Expiry: {expiry_date} | Nifty ≈ {nifty_spot}")
    else:
        st.metric("📈 OI Ratio (P/C)", "Unavailable")

with c4:
    s_bull = sum(1 for v in sectors.values() if v and v > 0)
    s_bear = sum(1 for v in sectors.values() if v and v < 0)
    st.metric("🏭 Sectors", f"{s_bull} green / {s_bear} red")

# ── Expandable detail tables ──
col_left, col_right = st.columns(2)

with col_left:
    with st.expander("🔍 Nifty Top 10 Stock Changes"):
        if top10:
            df_top10 = pd.DataFrame(
                [(k, f"{v:+.2f}%" if v else "N/A") for k, v in top10.items()],
                columns=["Stock", "Change"]
            )
            st.dataframe(df_top10, use_container_width=True, hide_index=True)
        else:
            st.write("Data unavailable")

with col_right:
    with st.expander("🔍 Sector Index Changes"):
        if sectors:
            df_sec = pd.DataFrame(
                [(k, f"{v:+.2f}%" if v else "N/A") for k, v in sectors.items()],
                columns=["Sector", "Change"]
            )
            st.dataframe(df_sec, use_container_width=True, hide_index=True)
        else:
            st.write("Data unavailable")

st.divider()

# ─────────────────────────────────────────────
# MANUAL INPUT — only Advance-Decline
# ─────────────────────────────────────────────
st.subheader("⌨️ One Manual Input Required")
st.caption("All other signals are auto-fetched. Only Advance-Decline has no free public API.")

col_a, col_b = st.columns(2)
with col_a:
    advances = st.number_input("🟢 Advances (NSE)", min_value=0, value=0, step=1)
with col_b:
    declines = st.number_input("🔴 Declines (NSE)", min_value=0, value=0, step=1)

st.caption("👉 Find this on [nseindia.com](https://www.nseindia.com) → Market → Advances/Declines")

st.divider()

# ─────────────────────────────────────────────
# SCORING + OUTPUT
# ─────────────────────────────────────────────
if st.button("🚀 Calculate Sentiment & Get Trade Signal", type="primary"):

    # ── Score each factor ──
    vix_adj, vix_label     = score_vix(vix)
    vix_blocked            = vix_adj == -999

    s_nifty, l_nifty, n_up, n_down = score_nifty_breadth(top10)
    s_oi,    l_oi                   = score_oi_ratio(oi_ratio)
    s_adv,   l_adv                  = score_adv_dec(advances, declines)
    s_sec,   l_sec, sec_up, sec_dn  = score_sectors(sectors)

    raw_score = s_nifty + s_oi + s_adv + s_sec
    final_score = max(0, raw_score + (vix_adj if not vix_blocked else 0))

    details = {
        "Nifty Breadth":  l_nifty,
        "OI Ratio (P/C)": l_oi,
        "Advance-Decline": l_adv,
        "Sector Heatmap": l_sec,
    }

    # ── Rule breakdown ──
    st.subheader("📌 Signal Breakdown")
    for k, v in details.items():
        color_signal(k, v)

    st.markdown(f"**VIX Filter:** :{'red' if vix_blocked else ('orange' if 'Elevated' in vix_label else 'green')}[{vix_label}]")

    # ── Score display ──
    st.divider()
    if vix_blocked:
        st.error(f"## 🚫 VIX Override — Score suppressed")
    elif final_score >= 70:
        st.success(f"## 🟢 Sentiment Score: **{final_score:.1f} / 100**")
    elif final_score <= 40:
        st.error(f"## 🔴 Sentiment Score: **{final_score:.1f} / 100**")
    else:
        st.warning(f"## 🟡 Sentiment Score: **{final_score:.1f} / 100**")

    # ── Gauge chart ──
    fig, ax = plt.subplots(figsize=(5, 2.5), facecolor="#0e1117")
    score_val = min(final_score, 100)
    zones = [40, 30, 30]
    colors_z = ["#ff4444", "#ffd700", "#00e5a0"]
    ax.barh(0, 100, color="#1a1a2e", height=0.5, left=0)
    left = 0
    for z, c in zip(zones, colors_z):
        ax.barh(0, z, color=c, height=0.5, left=left, alpha=0.3)
        left += z
    ax.barh(0, score_val, color="#00e5a0" if score_val >= 70 else ("#ffd700" if score_val >= 40 else "#ff4444"),
            height=0.3)
    ax.set_xlim(0, 100)
    ax.set_yticks([])
    ax.set_xlabel("Score", color="white")
    ax.tick_params(colors="white")
    ax.spines[:].set_visible(False)
    ax.set_facecolor("#0e1117")
    ax.set_title(f"Sentiment Score: {final_score:.1f}/100", color="white", fontsize=13)
    st.pyplot(fig)
    plt.close(fig)

    # ── Trade recommendation ──
    st.divider()
    st.subheader("🎯 Trade Recommendation")
    trade = get_trade_recommendation(final_score, details, vix_blocked)

    if trade["type"] == "BLOCKED":
        st.error(trade["message"])
    elif trade["type"] == "DIRECTIONAL":
        st.success(trade["message"])
    else:
        st.warning(trade["message"])

    st.info(f"**Suggested Delta:** {trade['delta']}")

    # ── Pie charts side by side ──
    st.divider()
    f2, (ax1, ax2) = plt.subplots(1, 2, figsize=(8, 3.5), facecolor="#0e1117")

    for ax in (ax1, ax2):
        ax.set_facecolor("#0e1117")

    if advances + declines > 0:
        ax1.pie([advances, declines], labels=["Advances", "Declines"],
                autopct="%1.1f%%", colors=["#00e5a0", "#ff4444"],
                textprops={"color": "white"})
        ax1.set_title("Advance-Decline", color="white")
    else:
        ax1.text(0.5, 0.5, "No A-D data", ha="center", va="center", color="gray")
        ax1.set_title("Advance-Decline", color="white")

    if sec_up + sec_dn > 0:
        ax2.pie([sec_up, sec_dn], labels=["Bull Sectors", "Bear Sectors"],
                autopct="%1.1f%%", colors=["#00e5a0", "#ff4444"],
                textprops={"color": "white"})
        ax2.set_title("Sector Heatmap", color="white")
    else:
        ax2.text(0.5, 0.5, "No sector data", ha="center", va="center", color="gray")
        ax2.set_title("Sector Heatmap", color="white")

    f2.patch.set_facecolor("#0e1117")
    st.pyplot(f2)
    plt.close(f2)

    # ── Save to history ──
    if "history" not in st.session_state:
        st.session_state.history = []

    st.session_state.history.append({
        "Time (IST)":  ist_now().strftime("%H:%M:%S"),
        "VIX":         vix or "N/A",
        "OI Ratio":    oi_ratio or "N/A",
        "Score":       round(final_score, 1),
        "Signal":      trade["message"],
        "Delta":       trade["delta"],
    })

# ─────────────────────────────────────────────
# HISTORY
# ─────────────────────────────────────────────
if st.session_state.get("history"):
    st.divider()
    st.subheader("📜 Session Trade Log")
    df_hist = pd.DataFrame(st.session_state.history)
    st.dataframe(df_hist, use_container_width=True, hide_index=True)

    if st.button("🗑️ Clear History"):
        st.session_state.history = []
        st.rerun()

# ─────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────
st.divider()
st.caption(
    "⚠️ This tool is for educational purposes only. "
    "Not SEBI-registered investment advice. "
    "Always use stop-losses and trade within your risk limits."
)