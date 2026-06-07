import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# ── Configuración de página ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Gold Macro Dashboard",
    page_icon="🥇",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── API Keys ─────────────────────────────────────────────────────────────────
GOLD_API_KEY = st.secrets.get("GOLD_API_KEY", "0ed3656e2b327a14900c3b46028586d569c40e529e0049ae95929a171b5d320e")
FRED_API_KEY = st.secrets.get("FRED_API_KEY", "")  # Gratis en fred.stlouisfed.org

# ── Estilos CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-header { font-size: 2rem; font-weight: 600; color: #BA7517; margin-bottom: 0; }
    .sub-header  { font-size: 0.9rem; color: #888; margin-bottom: 1.5rem; }
    .metric-container { background: #f8f9fa; border-radius: 12px; padding: 1rem 1.2rem; border: 1px solid #eee; }
    .signal-bullish { background: #EAF3DE; border-left: 4px solid #3B6D11; padding: 10px 14px; border-radius: 8px; margin-bottom: 8px; }
    .signal-bearish { background: #FCEBEB; border-left: 4px solid #A32D2D; padding: 10px 14px; border-radius: 8px; margin-bottom: 8px; }
    .signal-neutral { background: #FAEEDA; border-left: 4px solid #BA7517; padding: 10px 14px; border-radius: 8px; margin-bottom: 8px; }
    .signal-name  { font-size: 0.75rem; color: #666; margin-bottom: 2px; }
    .signal-val   { font-size: 1.1rem; font-weight: 600; color: #222; }
    .signal-label { font-size: 0.75rem; margin-top: 2px; }
    .bullish-text { color: #3B6D11; } .bearish-text { color: #A32D2D; } .neutral-text { color: #854F0B; }
    .footer { font-size: 0.75rem; color: #aaa; text-align: center; margin-top: 2rem; }
</style>
""", unsafe_allow_html=True)

# ── Funciones de datos ────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def get_gold_price():
    try:
        r = requests.get(
            "https://www.goldapi.io/api/XAU/USD",
            headers={"x-access-token": GOLD_API_KEY},
            timeout=10
        )
        d = r.json()
        return {
            "price": d.get("price"),
            "change": d.get("ch", 0),
            "change_pct": d.get("chp", 0),
            "open": d.get("open_price"),
            "high": d.get("high_price"),
            "low": d.get("low_price"),
            "prev_close": d.get("prev_close_price"),
        }
    except Exception as e:
        return None

@st.cache_data(ttl=60)
def get_gold_history_days(days=10):
    results = []
    today = datetime.now()
    checked = 0
    offset = 0
    while len(results) < days and offset < 30:
        d = today - timedelta(days=offset)
        offset += 1
        if d.weekday() >= 5:
            continue
        date_str = d.strftime("%Y%m%d")
        try:
            r = requests.get(
                f"https://www.goldapi.io/api/XAU/USD/{date_str}",
                headers={"x-access-token": GOLD_API_KEY},
                timeout=8
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("price"):
                    results.append({"date": d.strftime("%m/%d"), "price": data["price"]})
        except:
            pass
    return list(reversed(results))

@st.cache_data(ttl=300)
def get_fred_series(series_id):
    try:
        if FRED_API_KEY:
            url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={FRED_API_KEY}&file_type=json&sort_order=desc&limit=1"
            r = requests.get(url, timeout=10)
            d = r.json()
            val = float(d["observations"][0]["value"])
            return val
        else:
            url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
            r = requests.get(url, timeout=10)
            lines = [l for l in r.text.strip().split("\n") if not l.startswith("DATE")]
            val = float(lines[-1].split(",")[1])
            return val
    except:
        return None

@st.cache_data(ttl=120)
def get_yahoo_quote(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=10d"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        d = r.json()
        meta = d["chart"]["result"][0]["meta"]
        closes = d["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        timestamps = d["chart"]["result"][0]["timestamp"]
        return {
            "price": meta.get("regularMarketPrice"),
            "closes": closes,
            "timestamps": timestamps
        }
    except:
        return None

# ── Lógica de señales ─────────────────────────────────────────────────────────

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

def calc_bull_score(dxy, real_yield, vix, breakeven):
    score, total = 0, 0
    if dxy is not None:
        total += 30
        score += 30 if dxy < 98 else 15 if dxy < 104 else 0
    if real_yield is not None:
        total += 30
        score += 30 if real_yield < 0.5 else 15 if real_yield < 1.5 else 0
    if vix is not None:
        total += 20
        score += 20 if vix > 25 else 10 if vix > 15 else 0
    if breakeven is not None:
        total += 20
        score += 20 if breakeven > 2.5 else 10 if breakeven > 2.0 else 0
    return round(score / total * 100) if total > 0 else 50

# ── Gauge con Plotly ──────────────────────────────────────────────────────────

def make_gauge(score):
    color = "#3B6D11" if score >= 70 else "#BA7517" if score >= 50 else "#A32D2D"
    label = "Sesgo alcista fuerte" if score >= 70 else "Sesgo mixto / neutral" if score >= 50 else "Sesgo bajista"
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number={"suffix": "/100", "font": {"size": 28, "color": color}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "#ccc", "tickvals": [0,25,50,75,100], "ticktext": ["0","25","50","75","100"]},
            "bar": {"color": color, "thickness": 0.25},
            "bgcolor": "white",
            "steps": [
                {"range": [0, 25],   "color": "#FCEBEB"},
                {"range": [25, 50],  "color": "#FAEEDA"},
                {"range": [50, 75],  "color": "#EAF3DE"},
                {"range": [75, 100], "color": "#C0DD97"},
            ],
            "threshold": {"line": {"color": color, "width": 3}, "thickness": 0.75, "value": score}
        },
        title={"text": label, "font": {"size": 13, "color": "#666"}},
        domain={"x": [0, 1], "y": [0, 1]}
    ))
    fig.update_layout(height=220, margin=dict(t=30, b=10, l=20, r=20), paper_bgcolor="rgba(0,0,0,0)")
    return fig

# ── Gráfico histórico oro ─────────────────────────────────────────────────────

def make_price_chart(history):
    if not history:
        return None
    df = pd.DataFrame(history)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["price"],
        mode="lines+markers",
        line=dict(color="#BA7517", width=2.5),
        marker=dict(size=6, color="#BA7517"),
        fill="tozeroy",
        fillcolor="rgba(186,117,23,0.07)",
        name="XAU/USD"
    ))
    fig.update_layout(
        height=260,
        margin=dict(t=10, b=30, l=60, r=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(tickprefix="$", gridcolor="rgba(0,0,0,0.06)"),
        xaxis=dict(gridcolor="rgba(0,0,0,0)"),
        showlegend=False
    )
    return fig

# ── Render de señal ───────────────────────────────────────────────────────────

def render_signal(name, val_str, signal_type, label):
    css_class  = f"signal-{signal_type}"
    text_class = f"{signal_type}-text"
    val_display = val_str if val_str else "—"
    st.markdown(f"""
    <div class="{css_class}">
      <div class="signal-name">{name}</div>
      <div class="signal-val">{val_display}</div>
      <div class="signal-label {text_class}">{label}</div>
    </div>
    """, unsafe_allow_html=True)

# ── MAIN ──────────────────────────────────────────────────────────────────────

st.markdown('<div class="main-header">🥇 Gold Macro Dashboard</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">XAU/USD · DXY · Yield real 10Y · VIX · Breakeven inflación · Señal alcista/bajista</div>', unsafe_allow_html=True)

col_ref, col_time = st.columns([1, 3])
with col_ref:
    if st.button("🔄 Actualizar datos"):
        st.cache_data.clear()
        st.rerun()
with col_time:
    st.markdown(f"<div style='font-size:12px;color:#aaa;padding-top:8px'>Última actualización: {datetime.now().strftime('%H:%M:%S')} · Auto-refresca cada 60s</div>", unsafe_allow_html=True)

st.divider()

# ── Carga de datos ────────────────────────────────────────────────────────────
with st.spinner("Cargando datos del mercado..."):
    gold_data   = get_gold_price()
    dxy_data    = get_yahoo_quote("DX-Y.NYB")
    vix_data    = get_yahoo_quote("%5EVIX")
    yield10y    = get_fred_series("DGS10")
    breakeven   = get_fred_series("T10YIE")
    history     = get_gold_history_days(10)

gold_price  = gold_data["price"]  if gold_data else None
dxy         = dxy_data["price"]   if dxy_data  else None
vix         = vix_data["price"]   if vix_data  else None
real_yield  = round(yield10y - breakeven, 2) if (yield10y and breakeven) else None

# ── Métricas principales ──────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)

with c1:
    if gold_price:
        delta = f"{gold_data['change']:+.2f} ({gold_data['change_pct']:+.2f}%)" if gold_data.get("change") is not None else None
        st.metric("🥇 Oro XAU/USD", f"${gold_price:,.2f}", delta=delta)
    else:
        st.metric("🥇 Oro XAU/USD", "Sin dato")

with c2:
    if dxy:
        label = "Dólar débil" if dxy < 100 else "Neutral" if dxy < 104 else "Dólar fuerte"
        st.metric("💵 DXY — Índice dólar", f"{dxy:.2f}", delta=label, delta_color="off")
    else:
        st.metric("💵 DXY — Índice dólar", "Sin dato")

with c3:
    if real_yield is not None:
        note = f"Nominal {yield10y:.2f}% · BE {breakeven:.2f}%"
        st.metric("📈 Yield real 10Y", f"{real_yield:.2f}%", delta=note, delta_color="off")
    elif yield10y:
        st.metric("📈 Yield 10Y", f"{yield10y:.2f}%")
    else:
        st.metric("📈 Yield real 10Y", "Sin dato")

with c4:
    if vix:
        nivel = "⚠ Pánico" if vix > 30 else "Elevado" if vix > 20 else "Bajo"
        st.metric("🌡 VIX — Volatilidad", f"{vix:.2f}", delta=nivel, delta_color="off")
    else:
        st.metric("🌡 VIX — Volatilidad", "Sin dato")

st.divider()

# ── Gauge + Señales ───────────────────────────────────────────────────────────
col_gauge, col_signals = st.columns([1, 1])

with col_gauge:
    st.markdown("**Señal general del oro**")
    score = calc_bull_score(dxy, real_yield, vix, breakeven)
    st.plotly_chart(make_gauge(score), use_container_width=True, config={"displayModeBar": False})

with col_signals:
    st.markdown("**Señales por indicador**")
    s1, l1 = get_signal("dxy",        dxy)
    s2, l2 = get_signal("real_yield", real_yield)
    s3, l3 = get_signal("vix",        vix)
    s4, l4 = get_signal("breakeven",  breakeven)
    render_signal("DXY — Índice del dólar",      f"{dxy:.2f}"        if dxy        else None, s1, l1)
    render_signal("Yield real 10Y (TIPS)",        f"{real_yield:.2f}%" if real_yield else None, s2, l2)
    render_signal("VIX — Volatilidad de mercado", f"{vix:.2f}"        if vix        else None, s3, l3)
    render_signal("Breakeven inflación 10Y",      f"{breakeven:.2f}%" if breakeven  else None, s4, l4)

st.divider()

# ── Gráfico histórico ─────────────────────────────────────────────────────────
st.markdown("**Precio del oro — últimos 10 días hábiles (USD/oz)**")
fig = make_price_chart(history)
if fig:
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
else:
    st.info("Sin datos históricos disponibles en este momento.")

# ── Tabla de referencia ───────────────────────────────────────────────────────
with st.expander("📖 Guía de interpretación"):
    st.markdown("""
| Indicador | Zona alcista para oro | Zona bajista |
|---|---|---|
| DXY (Índice dólar) | < 98 (dólar débil) | > 104 (dólar fuerte) |
| Yield real 10Y | < 0.5% | > 1.5% |
| VIX (volatilidad) | > 25 (pánico de mercado) | < 15 |
| Breakeven inflación | > 2.5% | < 2.0% |

**Nota:** el gauge combina los 4 indicadores con pesos: DXY 30%, Yield real 30%, VIX 20%, Inflación 20%.
    """)

st.markdown('<div class="footer">Gold-API · Yahoo Finance · FRED (St. Louis Fed) · Datos con delay de mercado · No es asesoría de inversión</div>', unsafe_allow_html=True)

# ── Auto-refresh cada 60 segundos ─────────────────────────────────────────────
time.sleep(1)
st.markdown("""
<script>
setTimeout(function(){ window.location.reload(); }, 60000);
</script>
""", unsafe_allow_html=True)
