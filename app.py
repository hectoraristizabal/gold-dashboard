import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

st.set_page_config(
    page_title="Gold Macro Dashboard",
    page_icon="🥇",
    layout="wide",
    initial_sidebar_state="collapsed"
)

GOLD_API_KEY = st.secrets.get("GOLD_API_KEY", "0ed3656e2b327a14900c3b46028586d569c40e529e0049ae95929a171b5d320e")
FRED_API_KEY = st.secrets.get("FRED_API_KEY", "")

st.markdown("""
<style>
    .main-header { font-size: 2rem; font-weight: 600; color: #BA7517; margin-bottom: 0; }
    .sub-header  { font-size: 0.9rem; color: #888; margin-bottom: 1.5rem; }
    .signal-bullish { background: #EAF3DE; border-left: 4px solid #3B6D11; padding: 10px 14px; border-radius: 8px; margin-bottom: 8px; }
    .signal-bearish { background: #FCEBEB; border-left: 4px solid #A32D2D; padding: 10px 14px; border-radius: 8px; margin-bottom: 8px; }
    .signal-neutral { background: #FAEEDA; border-left: 4px solid #BA7517; padding: 10px 14px; border-radius: 8px; margin-bottom: 8px; }
    .signal-name  { font-size: 0.75rem; color: #666; margin-bottom: 2px; }
    .signal-val   { font-size: 1.1rem; font-weight: 600; color: #222; }
    .signal-label { font-size: 0.75rem; margin-top: 2px; }
    .bullish-text { color: #3B6D11; } .bearish-text { color: #A32D2D; } .neutral-text { color: #854F0B; }
    .source-tag   { font-size: 0.7rem; color: #aaa; margin-top: 2px; }
    .footer       { font-size: 0.75rem; color: #aaa; text-align: center; margin-top: 2rem; }
</style>
""", unsafe_allow_html=True)

# ── FUENTES DE DATOS ──────────────────────────────────────────────────────────

HEADERS_BROWSER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "application/json",
}

@st.cache_data(ttl=60)
def get_gold_price():
    """Intenta múltiples fuentes para el precio del oro."""
    # 1) Gold-API
    try:
        r = requests.get(
            "https://www.goldapi.io/api/XAU/USD",
            headers={"x-access-token": GOLD_API_KEY, "Content-Type": "application/json"},
            timeout=10
        )
        if r.status_code == 200:
            d = r.json()
            if d.get("price"):
                return {"price": d["price"], "change": d.get("ch", 0),
                        "change_pct": d.get("chp", 0), "open": d.get("open_price"),
                        "high": d.get("high_price"), "low": d.get("low_price"),
                        "prev_close": d.get("prev_close_price"), "source": "Gold-API"}
    except Exception as e:
        pass

    # 2) Metals-API vía metals.live (proxy público)
    try:
        r = requests.get("https://metals.live/api/spot", headers=HEADERS_BROWSER, timeout=8)
        if r.status_code == 200:
            d = r.json()
            for item in d:
                if item.get("gold"):
                    price = float(item["gold"]) * 31.1035  # troy oz
                    return {"price": price, "change": None, "change_pct": None,
                            "open": None, "high": None, "low": None,
                            "prev_close": None, "source": "metals.live"}
    except:
        pass

    # 3) Yahoo Finance XAU=X (spot oro — equivalente a TVC:GOLD)
    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/XAU%3DX?interval=1d&range=2d",
            headers=HEADERS_BROWSER, timeout=10
        )
        if r.status_code == 200:
            d = r.json()
            meta = d["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice")
            prev  = meta.get("chartPreviousClose")
            if price:
                ch  = round(price - prev, 2) if prev else None
                chp = round(ch / prev * 100, 2) if (ch and prev) else None
                return {"price": price, "change": ch, "change_pct": chp,
                        "open": meta.get("regularMarketOpen"),
                        "high": meta.get("regularMarketDayHigh"),
                        "low":  meta.get("regularMarketDayLow"),
                        "prev_close": prev, "source": "Yahoo Finance (XAU=X spot)"}
    except:
        pass

    # 4) Frankfurter API (XAU en base USD)
    try:
        r = requests.get("https://api.frankfurter.app/latest?from=XAU&to=USD", timeout=8)
        if r.status_code == 200:
            d = r.json()
            price = d.get("rates", {}).get("USD")
            if price:
                return {"price": price, "change": None, "change_pct": None,
                        "open": None, "high": None, "low": None,
                        "prev_close": None, "source": "Frankfurter"}
    except:
        pass

    return None

@st.cache_data(ttl=60)
def get_gold_history(days=10):
    results = []
    # Yahoo Finance XAU=X (spot oro — equivalente a TVC:GOLD)
    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/XAU%3DX?interval=1d&range=20d",
            headers=HEADERS_BROWSER, timeout=10
        )
        if r.status_code == 200:
            d = r.json()
            closes = d["chart"]["result"][0]["indicators"]["quote"][0]["close"]
            timestamps = d["chart"]["result"][0]["timestamp"]
            pairs = [(t, c) for t, c in zip(timestamps, closes) if c is not None][-days:]
            for ts, price in pairs:
                dt = datetime.fromtimestamp(ts)
                results.append({"date": dt.strftime("%m/%d"), "price": round(price, 2)})
            return results, "Yahoo Finance (XAU=X spot)"
    except:
        pass

    # Fallback: Gold-API histórico
    for offset in range(days + 5):
        if len(results) >= days:
            break
        d = datetime.now() - timedelta(days=offset)
        if d.weekday() >= 5:
            continue
        date_str = d.strftime("%Y%m%d")
        try:
            r = requests.get(
                f"https://www.goldapi.io/api/XAU/USD/{date_str}",
                headers={"x-access-token": GOLD_API_KEY},
                timeout=6
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("price"):
                    results.append({"date": d.strftime("%m/%d"), "price": data["price"]})
        except:
            pass
    return list(reversed(results)), "Gold-API histórico"

@st.cache_data(ttl=300)
def get_fred_value(series_id):
    """FRED con múltiples métodos."""
    # 1) Con API key si está disponible
    if FRED_API_KEY:
        try:
            url = (f"https://api.stlouisfed.org/fred/series/observations"
                   f"?series_id={series_id}&api_key={FRED_API_KEY}"
                   f"&file_type=json&sort_order=desc&limit=5")
            r = requests.get(url, timeout=10)
            d = r.json()
            for obs in d.get("observations", []):
                try:
                    val = float(obs["value"])
                    return val, obs["date"]
                except:
                    continue
        except:
            pass

    # 2) CSV público de FRED (sin API key)
    try:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        r = requests.get(url, headers=HEADERS_BROWSER, timeout=12)
        if r.status_code == 200:
            lines = [l for l in r.text.strip().split("\n") if not l.startswith("DATE") and "." in l]
            for line in reversed(lines):
                parts = line.split(",")
                try:
                    val = float(parts[1])
                    return val, parts[0]
                except:
                    continue
    except:
        pass

    # 3) Yahoo Finance como fallback para yields
    yahoo_map = {
        "DGS10":   "%5ETNX",   # 10Y Treasury yield
        "T10YIE":  None,        # No hay equivalente directo en Yahoo
        "VIXCLS":  "%5EVIX",
        "DTWEXBGS": "DX-Y.NYB",
    }
    yf_symbol = yahoo_map.get(series_id)
    if yf_symbol:
        try:
            r = requests.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_symbol}?interval=1d&range=2d",
                headers=HEADERS_BROWSER, timeout=10
            )
            if r.status_code == 200:
                d = r.json()
                price = d["chart"]["result"][0]["meta"].get("regularMarketPrice")
                if price:
                    return price, datetime.now().strftime("%Y-%m-%d")
        except:
            pass

    return None, None

@st.cache_data(ttl=120)
def get_yahoo_quote(symbol):
    try:
        r = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d",
            headers=HEADERS_BROWSER, timeout=10
        )
        if r.status_code == 200:
            d = r.json()
            meta = d["chart"]["result"][0]["meta"]
            return meta.get("regularMarketPrice")
    except:
        return None
    return None

# ── SEÑALES ───────────────────────────────────────────────────────────────────

def get_signal(indicator, value):
    if value is None:
        return "neutral", "Sin dato"
    if indicator == "dxy":
        if value < 98:   return "bullish", "Alcista para oro"
        if value < 104:  return "neutral",  "Neutral"
        return "bearish", "Bajista para oro"
    if indicator == "real_yield":
        if value < 0.5:  return "bullish", "Alcista para oro"
        if value < 1.5:  return "neutral",  "Neutral"
        return "bearish", "Bajista para oro"
    if indicator == "vix":
        if value > 25:   return "bullish", "Pánico → refugio en oro"
        if value > 15:   return "neutral",  "Volatilidad moderada"
        return "neutral", "Baja volatilidad"
    if indicator == "breakeven":
        if value > 2.5:  return "bullish", "Inflación alta → alcista"
        if value > 2.0:  return "neutral",  "Inflación moderada"
        return "bearish", "Inflación baja"
    return "neutral", "—"

def calc_score(dxy, real_yield, vix, breakeven):
    score, total = 0, 0
    if dxy is not None:
        total += 30; score += 30 if dxy < 98 else 15 if dxy < 104 else 0
    if real_yield is not None:
        total += 30; score += 30 if real_yield < 0.5 else 15 if real_yield < 1.5 else 0
    if vix is not None:
        total += 20; score += 20 if vix > 25 else 10 if vix > 15 else 0
    if breakeven is not None:
        total += 20; score += 20 if breakeven > 2.5 else 10 if breakeven > 2.0 else 0
    return round(score / total * 100) if total > 0 else 50

def render_signal(name, val_str, sig_type, label):
    css = f"signal-{sig_type}"
    txt = f"{sig_type}-text"
    st.markdown(f"""
    <div class="{css}">
      <div class="signal-name">{name}</div>
      <div class="signal-val">{val_str or "—"}</div>
      <div class="signal-label {txt}">{label}</div>
    </div>""", unsafe_allow_html=True)

def make_gauge(score):
    color = "#3B6D11" if score >= 70 else "#BA7517" if score >= 50 else "#A32D2D"
    label = "Sesgo alcista fuerte" if score >= 70 else "Sesgo mixto / neutral" if score >= 50 else "Sesgo bajista"
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number={"suffix": "/100", "font": {"size": 28, "color": color}},
        gauge={
            "axis": {"range": [0, 100], "tickvals": [0,25,50,75,100]},
            "bar":  {"color": color, "thickness": 0.25},
            "bgcolor": "white",
            "steps": [
                {"range": [0,  25],  "color": "#FCEBEB"},
                {"range": [25, 50],  "color": "#FAEEDA"},
                {"range": [50, 75],  "color": "#EAF3DE"},
                {"range": [75, 100], "color": "#C0DD97"},
            ],
            "threshold": {"line": {"color": color, "width": 3}, "thickness": 0.75, "value": score}
        },
        title={"text": label, "font": {"size": 13, "color": "#666"}},
        domain={"x": [0,1], "y": [0,1]}
    ))
    fig.update_layout(height=220, margin=dict(t=30, b=10, l=20, r=20), paper_bgcolor="rgba(0,0,0,0)")
    return fig

def make_price_chart(history):
    if not history:
        return None
    df = pd.DataFrame(history)
    mn = df["price"].min() * 0.997
    mx = df["price"].max() * 1.003
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["price"],
        mode="lines+markers",
        line=dict(color="#BA7517", width=2.5),
        marker=dict(size=6, color="#BA7517"),
        fill="tozeroy", fillcolor="rgba(186,117,23,0.07)",
        hovertemplate="$%{y:,.2f}<extra></extra>"
    ))
    fig.update_layout(
        height=260, margin=dict(t=10, b=30, l=60, r=20),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(tickprefix="$", gridcolor="rgba(0,0,0,0.06)", range=[mn, mx]),
        xaxis=dict(gridcolor="rgba(0,0,0,0)"),
        showlegend=False
    )
    return fig

# ── HEADER ────────────────────────────────────────────────────────────────────
st.markdown('<div class="main-header">🥇 Gold Macro Dashboard</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">XAU/USD · DXY · Yield real 10Y · VIX · Breakeven inflación</div>', unsafe_allow_html=True)

col_btn, col_ts = st.columns([1, 4])
with col_btn:
    if st.button("🔄 Actualizar"):
        st.cache_data.clear()
        st.rerun()
with col_ts:
    st.markdown(f"<div style='font-size:12px;color:#aaa;padding-top:8px'>"
                f"Última actualización: {datetime.now().strftime('%H:%M:%S')} · Auto-refresca cada 60s</div>",
                unsafe_allow_html=True)

st.divider()

# ── CARGA DE DATOS ────────────────────────────────────────────────────────────
with st.spinner("Cargando datos del mercado..."):
    gold_data          = get_gold_price()
    history, hist_src  = get_gold_history(10)
    dxy,  dxy_date     = get_fred_value("DTWEXBGS")
    yield10y, y_date   = get_fred_value("DGS10")
    breakeven, be_date = get_fred_value("T10YIE")
    vix,  vix_date     = get_fred_value("VIXCLS")

    # Fallbacks Yahoo para DXY y VIX si FRED falla
    if dxy is None:
        dxy = get_yahoo_quote("DX-Y.NYB")
    if vix is None:
        vix = get_yahoo_quote("%5EVIX")

gold_price = gold_data["price"] if gold_data else None
real_yield = round(yield10y - breakeven, 2) if (yield10y and breakeven) else None

# ── ESTADO DE FUENTES ─────────────────────────────────────────────────────────
fuentes = []
fuentes.append(f"🥇 Oro: {gold_data['source'] if gold_data else '❌ Sin dato'}")
fuentes.append(f"💵 DXY: {'✓' if dxy else '❌'}")
fuentes.append(f"📈 Yield 10Y: {'✓' if yield10y else '❌'}")
fuentes.append(f"🌡 VIX: {'✓' if vix else '❌'}")
fuentes.append(f"📊 Breakeven: {'✓' if breakeven else '❌'}")
with st.expander("🔌 Estado de fuentes de datos", expanded=not gold_price):
    st.info("  ·  ".join(fuentes))
    if not gold_price:
        st.warning("""
**¿Por qué el oro aparece Sin dato?**
Gold-API a veces bloquea el IP de Streamlit Cloud. Soluciones:
1. Obtén una FRED API key gratis en [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html) y agrégala en Secrets como `FRED_API_KEY`
2. El sistema ya intenta Yahoo Finance (XAU=X spot) como alternativa automática
        """)

# ── MÉTRICAS ──────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)

with c1:
    if gold_price:
        delta = None
        if gold_data.get("change") is not None:
            delta = f"{gold_data['change']:+.2f} ({gold_data['change_pct']:+.2f}%)"
        st.metric("🥇 Oro XAU/USD", f"${gold_price:,.2f}", delta=delta)
        st.caption(f"Fuente: {gold_data.get('source','—')}")
    else:
        st.metric("🥇 Oro XAU/USD", "Sin dato")
        st.caption("Intentando Yahoo Finance XAU=X spot...")

with c2:
    if dxy:
        lbl = "Dólar débil ▼" if dxy < 100 else "Neutral →" if dxy < 104 else "Dólar fuerte ▲"
        st.metric("💵 DXY — Índice dólar", f"{dxy:.2f}", delta=lbl, delta_color="off")
    else:
        st.metric("💵 DXY — Índice dólar", "Sin dato")

with c3:
    if real_yield is not None:
        st.metric("📈 Yield real 10Y", f"{real_yield:.2f}%",
                  delta=f"Nominal {yield10y:.2f}% · BE {breakeven:.2f}%", delta_color="off")
    elif yield10y:
        st.metric("📈 Yield 10Y", f"{yield10y:.2f}%", delta="Breakeven no disponible", delta_color="off")
    else:
        st.metric("📈 Yield real 10Y", "Sin dato")

with c4:
    if vix:
        nivel = "⚠ Pánico" if vix > 30 else "Elevado" if vix > 20 else "Bajo"
        st.metric("🌡 VIX — Volatilidad", f"{vix:.2f}", delta=nivel, delta_color="off")
    else:
        st.metric("🌡 VIX — Volatilidad", "Sin dato")

st.divider()

# ── GAUGE + SEÑALES ───────────────────────────────────────────────────────────
col_g, col_s = st.columns([1, 1])

with col_g:
    st.markdown("**Señal general del oro**")
    score = calc_score(dxy, real_yield, vix, breakeven)
    st.plotly_chart(make_gauge(score), use_container_width=True, config={"displayModeBar": False})

with col_s:
    st.markdown("**Señales por indicador**")
    s1,l1 = get_signal("dxy",        dxy)
    s2,l2 = get_signal("real_yield", real_yield)
    s3,l3 = get_signal("vix",        vix)
    s4,l4 = get_signal("breakeven",  breakeven)
    render_signal("DXY — Índice del dólar",      f"{dxy:.2f}"         if dxy         else None, s1, l1)
    render_signal("Yield real 10Y (TIPS)",        f"{real_yield:.2f}%" if real_yield  else None, s2, l2)
    render_signal("VIX — Volatilidad de mercado", f"{vix:.2f}"         if vix         else None, s3, l3)
    render_signal("Breakeven inflación 10Y",      f"{breakeven:.2f}%"  if breakeven   else None, s4, l4)

st.divider()

# ── HISTÓRICO ─────────────────────────────────────────────────────────────────
st.markdown(f"**Precio del oro — últimos días hábiles (USD/oz)** · *{hist_src}*")
fig = make_price_chart(history)
if fig:
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
else:
    st.info("Sin datos históricos disponibles.")

# ── GUÍA ──────────────────────────────────────────────────────────────────────
with st.expander("📖 Guía de interpretación de señales"):
    st.markdown("""
| Indicador | Zona alcista para oro | Zona bajista |
|---|---|---|
| DXY (Índice dólar)    | < 98 (dólar débil)     | > 104 (dólar fuerte) |
| Yield real 10Y        | < 0.5%                  | > 1.5%               |
| VIX (volatilidad)     | > 25 (pánico mercado)  | < 15                 |
| Breakeven inflación   | > 2.5%                  | < 2.0%               |

El **gauge** combina los 4 indicadores: DXY 30% · Yield real 30% · VIX 20% · Inflación 20%.
    """)

st.markdown('<div class="footer">Gold-API · Yahoo Finance · FRED St. Louis Fed · Datos con delay de mercado · No es asesoría de inversión</div>',
            unsafe_allow_html=True)

time.sleep(1)
st.markdown("<script>setTimeout(()=>window.location.reload(),60000);</script>", unsafe_allow_html=True)
