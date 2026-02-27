import streamlit as st
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import math
import requests
from datetime import datetime, timedelta
import pytz

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
NIFTY_TOP10 = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
    "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS"
]

SECTOR_INDICES = {
    "IT":      "^CNXIT",
    "Bank":    "^NSEBANK",
    "Auto":    "^CNXAUTO",
    "Pharma":  "^CNXPHARMA",
    "FMCG":    "^CNXFMCG",
    "Metal":   "^CNXMETAL",
    "Realty":  "^CNXREALTY",
    "Energy":  "^CNXENERGY",
    "Infra":   "^CNXINFRA",
    "Media":   "^CNXMEDIA",
}

IST = pytz.timezone("Asia/Kolkata")

CHECKLIST = [
    ("Check India VIX",             "Below 15 = safe. 15–20 = reduce size. Above 20 = stay flat."),
    ("Check GIFT Nifty",            "Pre-market direction indicator. Large gap = cautious entry."),
    ("Mark Support & Resistance",   "Draw key S/R on 15-min chart before open."),
    ("Check economic calendar",     "Any RBI, CPI, Fed, or major earnings events today?"),
    ("Confirm margin available",    "Keep 20–30% buffer. Never max out margin."),
    ("Choose strategy for the day", "Iron Condor / Strangle / Bull Put / Bear Call — decide now."),
    ("Define stop-loss level",      "2× premium received = exit. Set trigger order before entry."),
    ("Set daily loss limit",        "If total P&L hits −X today, I stop. Decide the number now."),
    ("Plan entry window",           "No trades before 9:30 AM. Best window: 9:30–10:30 AM."),
    ("Set 3:20 PM exit reminder",   "All positions closed by 3:20 PM. No exceptions."),
]

# ─────────────────────────────────────────────
# TIME HELPERS
# ─────────────────────────────────────────────
def ist_now():
    return datetime.now(IST)

def get_market_status():
    now = ist_now()
    if now.weekday() >= 5:
        return "weekend"
    t = now.time()
    def T(s): return datetime.strptime(s, "%H:%M").time()
    if t < T("09:15"):  return "pre"
    if t < T("09:30"):  return "opening"
    if t < T("15:20"):  return "live"
    if t < T("15:30"):  return "closing"
    return "closed"

def next_market_open():
    d = ist_now()
    while True:
        d = d + timedelta(days=1)
        if d.weekday() < 5:
            break
    return d.strftime("%A, %d %b %Y at 09:15 AM IST")

def last_trading_day_label():
    now    = ist_now()
    status = get_market_status()
    d      = now - timedelta(days=1) if status in ("pre", "opening") else now
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%A, %d %b %Y")

# ─────────────────────────────────────────────
# DATA FETCHERS  — period="5d" ensures data
# is always available regardless of market hours
# ─────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def fetch_vix():
    try:
        data = yf.Ticker("^INDIAVIX").history(period="5d", interval="1d")
        if data.empty:
            return None, None
        latest = round(float(data["Close"].iloc[-1]), 2)
        prev   = round(float(data["Close"].iloc[-2]), 2) if len(data) > 1 else None
        return latest, prev
    except Exception:
        return None, None

@st.cache_data(ttl=300, show_spinner=False)
def fetch_nifty_top10():
    try:
        data = yf.download(NIFTY_TOP10, period="5d", interval="1d",
                           progress=False, auto_adjust=True)["Close"]
        results = {}
        for ticker in NIFTY_TOP10:
            name = ticker.replace(".NS", "")
            try:
                prev  = float(data[ticker].iloc[-2])
                today = float(data[ticker].iloc[-1])
                results[name] = round(((today - prev) / prev) * 100, 2)
            except Exception:
                results[name] = None
        return results
    except Exception:
        return {}

@st.cache_data(ttl=300, show_spinner=False)
def fetch_sectors():
    try:
        tickers = list(SECTOR_INDICES.values())
        data = yf.download(tickers, period="5d", interval="1d",
                           progress=False, auto_adjust=True)["Close"]
        results = {}
        for sector, sym in SECTOR_INDICES.items():
            try:
                prev  = float(data[sym].iloc[-2])
                today = float(data[sym].iloc[-1])
                results[sector] = round(((today - prev) / prev) * 100, 2)
            except Exception:
                results[sector] = None
        return results
    except Exception:
        return {}

@st.cache_data(ttl=300, show_spinner=False)
def fetch_oi_ratio():
    try:
        nifty = yf.Ticker("^NSEI")
        expirations = nifty.options
        if not expirations:
            return None
        chain   = nifty.option_chain(expirations[0])
        put_oi  = int(chain.puts["openInterest"].sum())
        call_oi = int(chain.calls["openInterest"].sum())
        if call_oi == 0:
            return None
        spot = nifty.history(period="5d", interval="1d")
        current_price = round(float(spot["Close"].iloc[-1]), 2) if not spot.empty else "N/A"
        return round(put_oi / call_oi, 3), put_oi, call_oi, expirations[0], current_price
    except Exception:
        return None

@st.cache_data(ttl=60, show_spinner=False)
def fetch_live_nse_pcr():
    """Fetch live PCR directly from NSE option chain (your original approach — more accurate)."""
    url = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "application/json",
        "Referer": "https://www.nseindia.com/",
    }
    try:
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        resp = session.get(url, headers=headers, timeout=10)
        data = resp.json()
        put_oi, call_oi = 0, 0
        for item in data["records"]["data"]:
            if "PE" in item: put_oi  += item["PE"]["openInterest"]
            if "CE" in item: call_oi += item["CE"]["openInterest"]
        if call_oi == 0:
            return None
        return round(put_oi / call_oi, 3)
    except Exception:
        return None


def score_vix(vix):
    if vix is None:  return 0,    "Unknown"
    if vix > 20:     return -999, f"{vix} 🔴 DANGER — Avoid selling"
    if vix > 15:     return -10,  f"{vix} 🟡 Elevated — Reduce size"
    return 0, f"{vix} 🟢 Safe zone"

def score_nifty_breadth(stock_changes):
    up   = sum(1 for v in stock_changes.values() if v is not None and v > 0)
    down = sum(1 for v in stock_changes.values() if v is not None and v < 0)
    if not (up + down):
        return 15, "15 Neutral", up, down
    if up >= 6:
        pts = round((up / 10) * 30, 1)
        return pts, f"{pts} Bullish ({up}/10 up)", up, down
    if down >= 6:
        pts = round((down / 10) * 30, 1)
        return pts, f"{pts} Bearish ({down}/10 down)", up, down
    return 15, f"15 Neutral ({up} up / {down} down)", up, down

def score_oi_ratio(ratio):
    if ratio is None:
        return 15, "15 Neutral (data unavailable)"
    if ratio > 1:
        pts = round(min(30, (ratio - 1) * 30 + 15), 1)
        return pts, f"{pts} Bullish (OI ratio {ratio})"
    if ratio < 0.7:
        pts = round(min(30, (1 - ratio) * 30 + 15), 1)
        return pts, f"{pts} Bearish (OI ratio {ratio})"
    return 15, f"15 Neutral (OI ratio {ratio})"

def score_adv_dec(advances, declines):
    if advances == 0 and declines == 0: return 10, "10 Neutral"
    if declines == 0:  return 20, "20 Bullish (all advances)"
    if advances == 0:  return 20, "20 Bearish (all declines)"
    ratio    = advances / declines
    strength = min(1, abs(math.log(ratio)))
    pts      = round(strength * 20, 1)
    if ratio > 1.1:   return pts, f"{pts} Bullish ({advances}A / {declines}D)"
    if ratio < 0.9:   return pts, f"{pts} Bearish ({advances}A / {declines}D)"
    return 10, f"10 Neutral ({advances}A / {declines}D)"

def score_sectors(sector_changes):
    bull = sum(1 for v in sector_changes.values() if v is not None and v > 0)
    bear = sum(1 for v in sector_changes.values() if v is not None and v < 0)
    if not (bull + bear):
        return 10, "10 Neutral", bull, bear
    if bull > 0 and bear > 0:
        ratio    = bull / bear
        strength = min(1, abs(math.log(ratio)))
        pts      = round(strength * 20, 1)
        if ratio > 1.1:  return pts, f"{pts} Bullish ({bull}🟢 / {bear}🔴)", bull, bear
        if ratio < 0.9:  return pts, f"{pts} Bearish ({bull}🟢 / {bear}🔴)", bull, bear
        return 10, f"10 Neutral ({bull}🟢 / {bear}🔴)", bull, bear
    if bull > bear:  return 20, f"20 Bullish ({bull}🟢 / {bear}🔴)", bull, bear
    return 20, f"20 Bearish ({bull}🟢 / {bear}🔴)", bull, bear

def get_trade_recommendation(score, details, vix_blocked):
    if vix_blocked:
        return {"type": "BLOCKED",
                "message": "🚫 VIX too high — Do NOT sell options today",
                "delta": "Stay flat"}
    bullish = sum("Bullish" in v for v in details.values())
    bearish = sum("Bearish" in v for v in details.values())
    if abs(bullish - bearish) <= 1 or score < 65:
        return {"type": "FLAT",
                "message": "⚖️ Mixed signals → Sell BOTH sides (Iron Condor / Strangle)",
                "delta": "10–20Δ CE & PE"}
    direction = "PUT side (Bullish)" if bullish > bearish else "CALL side (Bearish)"
    if score >= 80:
        return {"type": "DIRECTIONAL",
                "message": f"🔥 Strong edge → Sell {direction}",
                "delta": "0.30–0.40Δ"}
    return {"type": "DIRECTIONAL",
            "message": f"✅ Decent edge → Sell {direction}",
            "delta": "0.30Δ"}


def get_param_signals(details, vix_label, vix_blocked):
    """
    For each parameter, return what option action it suggests individually.
    Returns list of dicts: {param, signal_text, action, emoji}
    """
    rows = []

    # VIX
    if vix_blocked:
        rows.append({"Parameter": "VIX Filter", "Reading": vix_label,
                     "Signal": "🚫 DANGER", "Option Action": "Stay FLAT — no selling",
                     "Delta Guidance": "—"})
    elif "Elevated" in vix_label:
        rows.append({"Parameter": "VIX Filter", "Reading": vix_label,
                     "Signal": "🟡 Caution", "Option Action": "Sell far OTM only / reduce size",
                     "Delta Guidance": "< 0.15Δ"})
    else:
        rows.append({"Parameter": "VIX Filter", "Reading": vix_label,
                     "Signal": "🟢 Safe", "Option Action": "Normal selling allowed",
                     "Delta Guidance": "Up to 0.30–0.40Δ"})

    param_map = {
        "Nifty Breadth":   "Nifty Top 10",
        "OI Ratio (P/C)":  "PCR / OI Ratio",
        "Advance-Decline": "Advance-Decline",
        "Sector Heatmap":  "Sector Heatmap",
    }

    for key, display in param_map.items():
        text = details.get(key, "Neutral")
        if "Bullish" in text:
            action = "Sell PE (Put) — market likely to go UP"
            delta  = "0.25–0.35Δ PE"
            signal = "🟢 Bullish"
        elif "Bearish" in text:
            action = "Sell CE (Call) — market likely to go DOWN"
            delta  = "0.25–0.35Δ CE"
            signal = "🔴 Bearish"
        else:
            action = "Sell both sides — no directional edge"
            delta  = "10–20Δ CE & PE"
            signal = "🟡 Neutral"
        rows.append({"Parameter": display, "Reading": text,
                     "Signal": signal, "Option Action": action,
                     "Delta Guidance": delta})
    return rows



def color_signal(label, text):
    if "Bullish" in text:   st.markdown(f"**{label}:** :green[{text}]")
    elif "Bearish" in text: st.markdown(f"**{label}:** :red[{text}]")
    else:                   st.markdown(f"**{label}:** :orange[{text}]")

# ─────────────────────────────────────────────
# UI COMPONENTS
# ─────────────────────────────────────────────
def render_data_cards(vix_tuple, top10, sectors, oi_data, heading):
    vix      = vix_tuple[0]
    vix_prev = vix_tuple[1]
    oi_ratio = oi_data[0] if oi_data else None
    expiry   = oi_data[3] if oi_data else "N/A"
    spot     = oi_data[4] if oi_data else "N/A"

    st.subheader(heading)
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        color = "normal" if (vix and vix < 15) else ("off" if (vix and vix < 20) else "inverse")
        st.metric("🌡️ India VIX", vix or "N/A",
                  delta=f"prev {vix_prev}" if vix_prev else None,
                  delta_color=color)
    with c2:
        up   = sum(1 for v in top10.values() if v and v > 0)
        down = sum(1 for v in top10.values() if v and v < 0)
        st.metric("📊 Nifty Top 10", f"{up} up / {down} down")
    with c3:
        d_label = "Bullish" if (oi_ratio and oi_ratio > 1) else ("Bearish" if (oi_ratio and oi_ratio < 0.7) else "Neutral")
        d_color = "normal" if (oi_ratio and oi_ratio > 1) else ("inverse" if (oi_ratio and oi_ratio < 0.7) else "off")
        st.metric("📈 OI Ratio (P/C)", oi_ratio or "N/A", delta=d_label, delta_color=d_color)
        if oi_data: st.caption(f"Expiry: {expiry} | Nifty ≈ {spot}")
    with c4:
        sb = sum(1 for v in sectors.values() if v and v > 0)
        sr = sum(1 for v in sectors.values() if v and v < 0)
        st.metric("🏭 Sectors", f"{sb}🟢 / {sr}🔴")

    col_l, col_r = st.columns(2)
    with col_l:
        with st.expander("🔍 Nifty Top 10 Detail"):
            if top10:
                df = pd.DataFrame([(k, f"{v:+.2f}%" if v else "N/A")
                                   for k, v in top10.items()], columns=["Stock", "Change"])
                st.dataframe(df, use_container_width=True, hide_index=True)
    with col_r:
        with st.expander("🔍 Sector Detail"):
            if sectors:
                df = pd.DataFrame([(k, f"{v:+.2f}%" if v else "N/A")
                                   for k, v in sectors.items()], columns=["Sector", "Change"])
                st.dataframe(df, use_container_width=True, hide_index=True)


def render_checklist():
    st.subheader("✅ Pre-Market Preparation Checklist")
    st.caption("Work through this before 9:30 AM. Click each item to check it off.")

    if "checklist_state" not in st.session_state:
        st.session_state.checklist_state = [False] * len(CHECKLIST)

    done = sum(st.session_state.checklist_state)
    st.progress(done / len(CHECKLIST), text=f"{done} / {len(CHECKLIST)} completed")
    st.write("")

    for i, (title, desc) in enumerate(CHECKLIST):
        checked = st.checkbox(
            f"**{title}** — {desc}",
            value=st.session_state.checklist_state[i],
            key=f"chk_{i}"
        )
        st.session_state.checklist_state[i] = checked

    if done == len(CHECKLIST):
        st.success("🎯 All checks done! You're ready for the session.")

    if st.button("🔄 Reset Checklist"):
        st.session_state.checklist_state = [False] * len(CHECKLIST)
        st.rerun()


def render_live_scoring(vix_tuple, top10, sectors, oi_data):
    vix      = vix_tuple[0]

    # ── PCR Source Toggle (your original approach) ──
    st.divider()
    st.subheader("📈 PCR Source")
    use_live_pcr = st.toggle("🔴 Use Live NSE PCR (direct from NSE option chain)", value=True,
                              help="Fetches Put/Call ratio directly from NSE — more accurate than yfinance.")
    if use_live_pcr:
        with st.spinner("Fetching live PCR from NSE..."):
            live_pcr = fetch_live_nse_pcr()
        if live_pcr is not None:
            st.metric("Live NIFTY PCR", live_pcr,
                      help="Source: NSE option chain. PCR > 1 = bullish, < 0.7 = bearish.")
            oi_ratio = live_pcr
        else:
            st.warning("⚠️ Live PCR unavailable — falling back to yfinance OI data or enter manually below.")
            oi_ratio = oi_data[0] if oi_data else None
            if oi_ratio:
                st.caption(f"yfinance OI ratio: {oi_ratio}")
            else:
                oi_ratio = st.number_input("PCR Ratio (Manual fallback)", min_value=0.0,
                                            step=0.01, key="manual_pcr_fallback")
    else:
        oi_ratio = oi_data[0] if oi_data else None
        st.caption(f"Using yfinance OI ratio: {oi_ratio or 'Not available'}")
        if not oi_ratio:
            oi_ratio = st.number_input("PCR Ratio (Manual)", min_value=0.0,
                                        step=0.01, key="manual_pcr_direct")

    # ── Advance-Decline ──
    st.divider()
    st.subheader("⌨️ Manual Input: Advance-Decline")
    st.caption("No free public API available — get from [nseindia.com](https://www.nseindia.com) → Market → Advances/Declines")
    col_a, col_b = st.columns(2)
    with col_a:
        advances = st.number_input("🟢 Advances", min_value=0, value=0, step=1)
    with col_b:
        declines = st.number_input("🔴 Declines", min_value=0, value=0, step=1)

    st.divider()
    if st.button("🚀 Calculate Sentiment & Get Trade Signal", type="primary"):

        vix_adj, vix_label              = score_vix(vix)
        vix_blocked                     = vix_adj == -999
        s_nifty, l_nifty, n_up, n_down  = score_nifty_breadth(top10)
        s_oi,    l_oi                   = score_oi_ratio(oi_ratio)
        s_adv,   l_adv                  = score_adv_dec(advances, declines)
        s_sec,   l_sec, sec_up, sec_dn  = score_sectors(sectors)

        final_score = max(0, s_nifty + s_oi + s_adv + s_sec + (vix_adj if not vix_blocked else 0))

        details = {
            "Nifty Breadth":   l_nifty,
            "OI Ratio (P/C)":  l_oi,
            "Advance-Decline": l_adv,
            "Sector Heatmap":  l_sec,
        }

        # ── Breakdown ──
        st.subheader("📌 Signal Breakdown")
        for k, v in details.items():
            color_signal(k, v)
        vix_color = "red" if vix_blocked else ("orange" if "Elevated" in vix_label else "green")
        st.markdown(f"**VIX Filter:** :{vix_color}[{vix_label}]")

        # ── Score ──
        st.divider()
        if vix_blocked:
            st.error("## 🚫 VIX Override — Score suppressed")
        elif final_score >= 70:
            st.success(f"## 🟢 Sentiment Score: **{final_score:.1f} / 100**")
        elif final_score <= 40:
            st.error(f"## 🔴 Sentiment Score: **{final_score:.1f} / 100**")
        else:
            st.warning(f"## 🟡 Sentiment Score: **{final_score:.1f} / 100**")

        # ── Gauge ──
        fig, ax = plt.subplots(figsize=(5, 1.8), facecolor="#0e1117")
        for lft, wid, c in [(0, 40, "#ff4444"), (40, 30, "#ffd700"), (70, 30, "#00e5a0")]:
            ax.barh(0, wid, left=lft, color=c, alpha=0.2, height=0.5)
        bar_c = "#00e5a0" if final_score >= 70 else ("#ffd700" if final_score >= 40 else "#ff4444")
        ax.barh(0, min(final_score, 100), color=bar_c, height=0.3)
        ax.set_xlim(0, 100); ax.set_yticks([]); ax.set_facecolor("#0e1117")
        ax.tick_params(colors="white"); ax.spines[:].set_visible(False)
        ax.set_xlabel("Score", color="white")
        ax.set_title(f"Score: {final_score:.1f} / 100", color="white")
        st.pyplot(fig); plt.close(fig)

        # ── Overall trade recommendation ──
        st.divider()
        st.subheader("🎯 Overall Trade Recommendation")
        trade = get_trade_recommendation(final_score, details, vix_blocked)
        if trade["type"] == "BLOCKED":        st.error(trade["message"])
        elif trade["type"] == "DIRECTIONAL":  st.success(trade["message"])
        else:                                 st.warning(trade["message"])
        st.info(f"**Suggested Delta:** {trade['delta']}")

        # ── Per-parameter option scoring ──
        st.divider()
        st.subheader("📋 Per-Parameter Option Signal")
        st.caption("What each individual indicator is telling you to sell — useful when signals conflict.")

        param_rows = get_param_signals(details, vix_label, vix_blocked)
        df_params = pd.DataFrame(param_rows)

        # Style the dataframe with color highlighting
        def highlight_signal(val):
            if "🟢" in str(val) or "Bullish" in str(val) or "PE" in str(val):
                return "background-color: #0d2e1e; color: #00e5a0"
            elif "🔴" in str(val) or "Bearish" in str(val) or "CE" in str(val):
                return "background-color: #2e0d1a; color: #ff4444"
            elif "🚫" in str(val) or "FLAT" in str(val) or "DANGER" in str(val):
                return "background-color: #2e1a0d; color: #ff8800"
            elif "🟡" in str(val) or "Neutral" in str(val) or "both" in str(val):
                return "background-color: #2a2a0d; color: #ffd700"
            return ""

        styled = df_params.style.applymap(highlight_signal, subset=["Signal", "Option Action"])
        st.dataframe(styled, use_container_width=True, hide_index=True)

        # ── Vote summary ──
        votes = {"Sell PE 🟢": 0, "Sell CE 🔴": 0, "Both sides 🟡": 0, "FLAT 🚫": 0}
        for row in param_rows:
            act = row["Option Action"]
            if "FLAT" in act or "DANGER" in act:  votes["FLAT 🚫"] += 1
            elif "PE" in act:                      votes["Sell PE 🟢"] += 1
            elif "CE" in act:                      votes["Sell CE 🔴"] += 1
            else:                                  votes["Both sides 🟡"] += 1

        st.caption("**Signal Vote Count:**  " + "  |  ".join(
            f"{k}: **{v}**" for k, v in votes.items() if v > 0
        ))

        # ── Charts ──
        st.divider()
        f2, (ax1, ax2) = plt.subplots(1, 2, figsize=(8, 3.5), facecolor="#0e1117")
        for ax in (ax1, ax2): ax.set_facecolor("#0e1117")
        if advances + declines > 0:
            ax1.pie([advances, declines], labels=["Advances", "Declines"],
                    autopct="%1.1f%%", colors=["#00e5a0", "#ff4444"],
                    textprops={"color": "white"})
        else:
            ax1.text(0.5, 0.5, "No A-D data entered", ha="center", va="center", color="gray", fontsize=9)
        ax1.set_title("Advance-Decline", color="white")

        sec_u = sum(1 for v in sectors.values() if v and v > 0)
        sec_d = sum(1 for v in sectors.values() if v and v < 0)
        if sec_u + sec_d > 0:
            ax2.pie([sec_u, sec_d], labels=["Bull Sectors", "Bear Sectors"],
                    autopct="%1.1f%%", colors=["#00e5a0", "#ff4444"],
                    textprops={"color": "white"})
        else:
            ax2.text(0.5, 0.5, "No sector data", ha="center", va="center", color="gray", fontsize=9)
        ax2.set_title("Sector Heatmap", color="white")
        f2.patch.set_facecolor("#0e1117")
        st.pyplot(f2); plt.close(f2)

        # ── History ──
        if "history" not in st.session_state:
            st.session_state.history = []
        st.session_state.history.append({
            "Time (IST)": ist_now().strftime("%H:%M:%S"),
            "VIX":        vix or "N/A",
            "OI Ratio":   oi_ratio or "N/A",
            "Score":      round(final_score, 1),
            "Signal":     trade["message"],
            "Delta":      trade["delta"],
        })

    if st.session_state.get("history"):
        st.divider()
        st.subheader("📜 Session Trade Log")
        st.dataframe(pd.DataFrame(st.session_state.history),
                     use_container_width=True, hide_index=True)
        if st.button("🗑️ Clear History"):
            st.session_state.history = []
            st.rerun()


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
st.set_page_config(page_title="Option Selling Dashboard", page_icon="📊", layout="wide")
st.title("📊 Intraday Option Selling Dashboard")

now    = ist_now()
status = get_market_status()
st.caption(f"🕐 {now.strftime('%d %b %Y  %H:%M:%S IST')}")

# ── Fetch data (period='5d' always returns recent data regardless of market hours) ──
with st.spinner("📡 Fetching market data..."):
    vix_tuple = fetch_vix()
    top10     = fetch_nifty_top10()
    sectors   = fetch_sectors()
    oi_data   = fetch_oi_ratio()

# ─────────────────────────────────────────────
# MANUAL OVERRIDE PANEL
# ─────────────────────────────────────────────
with st.expander("🛠️ Manual Data Override — Edit any fetched value or fill missing data", expanded=False):
    st.caption("All fields are pre-filled with fetched data. Edit any value you're not satisfied with, or fill in data that failed to fetch.")

    ov_col1, ov_col2 = st.columns(2)

    # ── VIX Override ──
    with ov_col1:
        st.markdown("**🌡️ India VIX**")
        vix_fetched = vix_tuple[0]
        vix_prev_fetched = vix_tuple[1]
        vix_override = st.number_input(
            "VIX Value",
            min_value=0.0, max_value=100.0, step=0.01,
            value=float(vix_fetched) if vix_fetched else 0.0,
            key="ov_vix",
            help="Fetched automatically. Override if value looks wrong."
        )
        vix_prev_override = st.number_input(
            "VIX Prev Close",
            min_value=0.0, max_value=100.0, step=0.01,
            value=float(vix_prev_fetched) if vix_prev_fetched else 0.0,
            key="ov_vix_prev",
        )
        if vix_fetched:
            st.caption(f"✅ Fetched: {vix_fetched} (prev: {vix_prev_fetched})")
        else:
            st.caption("⚠️ Fetch failed — please enter manually")

    # ── OI Ratio Override ──
    with ov_col2:
        st.markdown("**📈 OI Ratio (Put/Call)**")
        oi_fetched_ratio   = oi_data[0] if oi_data else None
        oi_fetched_put     = oi_data[1] if oi_data else 0
        oi_fetched_call    = oi_data[2] if oi_data else 0
        oi_fetched_expiry  = oi_data[3] if oi_data else ""
        oi_fetched_spot    = oi_data[4] if oi_data else 0.0

        oi_put_override  = st.number_input("Put OI",  min_value=0, step=1000,
                                            value=int(oi_fetched_put),  key="ov_put_oi")
        oi_call_override = st.number_input("Call OI", min_value=0, step=1000,
                                            value=int(oi_fetched_call), key="ov_call_oi")
        oi_expiry_override = st.text_input("Expiry Date", value=oi_fetched_expiry or "", key="ov_expiry")
        oi_spot_override   = st.number_input("Nifty Spot", min_value=0.0, step=0.5,
                                              value=float(oi_fetched_spot) if oi_fetched_spot and oi_fetched_spot != "N/A" else 0.0,
                                              key="ov_spot")
        if oi_fetched_ratio:
            st.caption(f"✅ Fetched ratio: {oi_fetched_ratio}")
        else:
            st.caption("⚠️ Fetch failed — please enter Put OI & Call OI manually")

    st.divider()
    ov_col3, ov_col4 = st.columns(2)

    # ── Top 10 Stocks Override ──
    with ov_col3:
        st.markdown("**📊 Nifty Top 10 — % Change**")
        top10_overrides = {}
        for ticker in NIFTY_TOP10:
            name = ticker.replace(".NS", "")
            fetched_val = top10.get(name)
            top10_overrides[name] = st.number_input(
                name,
                min_value=-20.0, max_value=20.0, step=0.01, format="%.2f",
                value=float(fetched_val) if fetched_val is not None else 0.0,
                key=f"ov_top10_{name}",
                help=f"Fetched: {fetched_val}%" if fetched_val is not None else "Not fetched"
            )
        if top10:
            st.caption(f"✅ Fetched {len([v for v in top10.values() if v is not None])}/10 stocks")
        else:
            st.caption("⚠️ Fetch failed — enter % changes manually")

    # ── Sectors Override ──
    with ov_col4:
        st.markdown("**🏭 Sector % Change**")
        sector_overrides = {}
        for sector in SECTOR_INDICES:
            fetched_val = sectors.get(sector)
            sector_overrides[sector] = st.number_input(
                sector,
                min_value=-20.0, max_value=20.0, step=0.01, format="%.2f",
                value=float(fetched_val) if fetched_val is not None else 0.0,
                key=f"ov_sec_{sector}",
                help=f"Fetched: {fetched_val}%" if fetched_val is not None else "Not fetched"
            )
        if sectors:
            st.caption(f"✅ Fetched {len([v for v in sectors.values() if v is not None])}/10 sectors")
        else:
            st.caption("⚠️ Fetch failed — enter % changes manually")

# ── Apply overrides: replace fetched data with user-edited values ──
# VIX
_vix_val  = st.session_state.get("ov_vix",      vix_tuple[0])
_vix_prev = st.session_state.get("ov_vix_prev", vix_tuple[1])
vix_tuple = (_vix_val if _vix_val != 0.0 else None,
             _vix_prev if _vix_prev != 0.0 else None)

# Top 10
_top10_ov = {n: st.session_state.get(f"ov_top10_{n}") for n in [t.replace(".NS","") for t in NIFTY_TOP10]}
top10 = {k: v for k, v in _top10_ov.items()}

# Sectors
_sec_ov = {s: st.session_state.get(f"ov_sec_{s}") for s in SECTOR_INDICES}
sectors = {k: v for k, v in _sec_ov.items()}

# OI
_put  = st.session_state.get("ov_put_oi",  oi_fetched_put  if oi_data else 0)
_call = st.session_state.get("ov_call_oi", oi_fetched_call if oi_data else 0)
_exp  = st.session_state.get("ov_expiry",  oi_fetched_expiry if oi_data else "")
_spot = st.session_state.get("ov_spot",    float(oi_fetched_spot) if (oi_data and oi_data[4] != "N/A") else 0.0)
if _put > 0 and _call > 0:
    oi_data = (round(_put / _call, 3), _put, _call, _exp, _spot)
else:
    oi_data = None

# ── Route by status ──
if status == "live":
    st.success("🟢 **Market LIVE** — Data refreshes every 5 min")
    render_data_cards(vix_tuple, top10, sectors, oi_data, "📡 Live Market Data")
    render_live_scoring(vix_tuple, top10, sectors, oi_data)

elif status == "opening":
    st.warning("🟡 **Opening Phase (9:15–9:30 AM)** — Wait before trading. Checking data is fine.")
    render_data_cards(vix_tuple, top10, sectors, oi_data, "📡 Today's Opening Data")
    st.divider()
    render_checklist()

elif status == "closing":
    st.error("🔴 **After 3:20 PM — Square off ALL positions now. No new entries.**")
    render_data_cards(vix_tuple, top10, sectors, oi_data, "📅 Today's Session Data")

elif status == "pre":
    st.info(f"🕐 **Pre-Market** — Market opens at 09:15 AM. Showing last session data.")
    day = last_trading_day_label()
    render_data_cards(vix_tuple, top10, sectors, oi_data, f"📅 Last Session Data ({day})")
    st.divider()
    render_checklist()

elif status in ("closed", "weekend"):
    label = "Weekend" if status == "weekend" else "Market Closed"
    st.info(f"🔒 **{label}** — Next session: {next_market_open()}")
    day = last_trading_day_label()
    render_data_cards(vix_tuple, top10, sectors, oi_data, f"📅 Last Session Data ({day})")
    st.divider()
    render_checklist()

# ── Footer ──
st.divider()
st.caption("⚠️ For educational purposes only. Not SEBI-registered investment advice. Always use stop-losses and trade within your risk limits.")