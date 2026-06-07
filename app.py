import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pytz
import time

st.set_page_config(
    page_title="Gold Macro Dashboard",
    page_icon="🥇",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── API Keys ──────────────────────────────────────────────────────────────────
TWELVE_DATA_KEY = st.secrets.get("TWELVE_DATA_KEY", "f589353e36df44e498cbb5e847f30015")
FRED_API_KEY    = st.secrets.get("FRED_API_KEY", "")

# ── Estilos ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-header  { font-size: 2rem; font-weight: 600; color: #BA7517; margin-bottom: 0; }
    .sub-header   { font-size: 0.9rem; color: #888; margin-bottom: 1.5rem; }
    .signal-bullish { background:#EAF3DE; border-left:4px solid #3B6D11; padding:10px 14px; border-radius:8px; margin-bottom:8px; }
    .signal-bearish { background:#FCEBEB; border-left:4px solid #A32D2D; padding:10px 14px; border-radius:8px; margin-bottom:8px; }
    .signal-neutral { background:#FAEEDA; border-left:4px solid #BA7517; padding:10px 14px; border-radius:8px; margin-bottom:8px; }
    .signal-name  { font-size:0.75rem; color:#666; margin-bottom:2px; }
    .signal-val   { font-size:1.1rem; font-weight:600; color:#222; }
    .signal-label { font-size:0.75rem; margin-top:2px; }
    .bullish-text { color:#3B6D11; } .bearish-text { color:#A32D2D; } .neutral-text { color:#854F0B; }
    .market-open  { background:#EAF3DE; border-radius:6px; padding:4px 10px; font-size:12px; color:#3B6D11; display:inline-block; }
    .market-closed{ background:#FCEBEB; border-radius:6px; padding:4px 10px; font-size:12px; color:#A32D2D; display:inline-block; }
    .footer       { font-size:0.75rem; color:#aaa; text-align:center; margin-top:2rem; }
</style>
""", unsafe_allow_html=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "application/json",
}

# ── Horario de mercado ────────────────────────────────────────────────────────
def is_gold_market_open():
    """El mercado del oro opera Dom 6pm ET a Vie 5pm ET."""
    et = pytz.timezone("America/New_York")
    now = datetime.now(et)
    wd = now.weekday()  # 0=Lun, 6=Dom
    h  = now.hour + now.minute / 60
    if wd == 5:                          # Sábado: cerrado
        return False
    if wd == 6 and h < 18:              # Domingo antes de 6pm: cerrado
        return False
    if wd == 4 and h >= 17:             # Viernes después de 5pm: cerrado
        return False
    return True

def get_refresh_seconds():
    """2 min si mercado abierto, 30 min si cerrado — optimiza los 800 req/día."""
    return 120 if is_gold_market_open() else 1800

# ── Twelve Data — precio spot XAU/USD ─────────────────────────────────────────
@st.cache_data(ttl=115)
def get_gold_price_twelvedata():
    try:
        # Precio actual
        r = requests.get(
            f"https://api.twelvedata.com/price?symbol=XAU/USD&apikey={TWELVE_DATA_KEY}",
            timeout=10
        )
        if r.status_code == 200:
            d = r.json()
            if d.get("price"):
                price = float(d["price"])
                # Quote para cambio del día
                r2 = requests.get(
                    f"https://api.twelvedata.com/quote?symbol=XAU/USD&apikey={TWELVE_DATA_KEY}",
                    timeout=10
                )
                change, change_pct, open_p, high, low, prev_close = None, None, None, None, None, None
                if r2.status_code == 200:
                    q = r2.json()
                    if not q.get("code"):  # sin error
                        change      = float(q.get("change",      0) or 0)
                        change_pct  = float(q.get("percent_change", 0) or 0)
                        open_p      = float(q.get("open",  price) or price)
                        high        = float(q.get("fifty_two_week", {}).get("high", price) or price)
                        low         = float(q.get("fifty_two_week", {}).get("low",  price) or price)
                        prev_close  = float(q.get("previous_close", price) or price)
                        high        = float(q.get("high",  price) or price)
                        low         = float(q.get("low",   price) or price)
                return {
                    "price": price, "change": change, "change_pct": change_pct,
                    "open": open_p, "high": high, "low": low,
                    "prev_close": prev_close, "source": "Twelve Data (XAU/USD spot)"
                }
    except Exception as e:
        pass
    return None

@st.cache_data(ttl=300)
def get_gold_history_twelvedata(days=12):
    try:
        r = requests.get(
            f"https://api.twelvedata.com/time_series?symbol=XAU/USD&interval=1day"
            f"&outputsize={days}&apikey={TWELVE_DATA_KEY}",
            timeout=12
        )
        if r.status_code == 200:
            d = r.json()
            if d.get("values"):
                results = []
                for v in reversed(d["values"]):
                    dt = datetime.strptime(v["datetime"], "%Y-%m-%d")
                    results.append({"date": dt.strftime("%m/%d"), "price": float(v["close"])})
                return results, "Twelve Data"
    except:
        pass
    return [], "Sin datos"

# ── FRED ──────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_fred_value(series_id):
    if FRED_API_KEY:
        try:
            url = (f"https://api.stlouisfed.org/fred/series/observations"
                   f"?series_id={series_id}&api_key={FRED_API_KEY}"
                   f"&file_type=json&sort_order=desc&limit=5")
            r = requests.get(url, timeout=10)
            for obs in r.json().get("observations", []):
                try:    return float(obs["value"]), obs["date"]
                except: continue
        except: pass
    try:
        r = requests.get(
            f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}",
            headers=HEADERS, timeout=12
        )
        if r.status_code == 200:
            lines = [l for l in r.text.strip().split("\n") if not l.startswith("DATE") and "." in l]
            for line in reversed(lines):
                parts = line.split(",")
                try:    return float(parts[1]), parts[0]
                except: continue
    except: pass
    return None, None

@st.cache_data(ttl=120)
def get_yahoo_quote(symbol):
    try:
        r = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2d",
            headers=HEADERS, timeout=10
        )
        if r.status_code == 200:
            return r.json()["chart"]["result"][0]["meta"].get("regularMarketPrice")
    except: pass
    return None

# ── Señales y gauge ───────────────────────────────────────────────────────────
def get_signal(ind, val):
    if val is None: return "neutral", "Sin dato"
    if ind == "dxy":
        return ("bullish","Alcista para oro") if val<98 else ("neutral","Neutral") if val<104 else ("bearish","Bajista para oro")
    if ind == "real_yield":
        return ("bullish","Alcista para oro") if val<0.5 else ("neutral","Neutral") if val<1.5 else ("bearish","Bajista para oro")
    if ind == "vix":
        return ("bullish","Pánico → refugio en oro") if val>25 else ("neutral","Volatilidad moderada") if val>15 else ("neutral","Baja volatilidad")
    if ind == "breakeven":
        return ("bullish","Inflación alta → alcista") if val>2.5 else ("neutral","Inflación moderada") if val>2.0 else ("bearish","Inflación baja")
    return "neutral","—"

def calc_score(dxy, ry, vix, be):
    s,t = 0,0
    if dxy is not None: t+=30; s+=30 if dxy<98 else 15 if dxy<104 else 0
    if ry  is not None: t+=30; s+=30 if ry<0.5  else 15 if ry<1.5   else 0
    if vix is not None: t+=20; s+=20 if vix>25   else 10 if vix>15   else 0
    if be  is not None: t+=20; s+=20 if be>2.5   else 10 if be>2.0   else 0
    return round(s/t*100) if t>0 else 50

def render_signal(name, desc, val_str, sig, label):
    st.markdown(f"""
    <div class="signal-{sig}">
      <div class="signal-name">{name} <span style='font-weight:normal;color:#999'>· {desc}</span></div>
      <div class="signal-val">{val_str or "—"}</div>
      <div class="signal-label {sig}-text">{label}</div>
    </div>""", unsafe_allow_html=True)

def make_gauge(score):
    color = "#3B6D11" if score>=70 else "#BA7517" if score>=50 else "#A32D2D"
    label = "Sesgo alcista fuerte" if score>=70 else "Sesgo mixto / neutral" if score>=50 else "Sesgo bajista"
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=score,
        number={"suffix":"/100","font":{"size":28,"color":color}},
        gauge={
            "axis":{"range":[0,100],"tickvals":[0,25,50,75,100]},
            "bar":{"color":color,"thickness":0.25},
            "bgcolor":"white",
            "steps":[
                {"range":[0,25],  "color":"#FCEBEB"},
                {"range":[25,50], "color":"#FAEEDA"},
                {"range":[50,75], "color":"#EAF3DE"},
                {"range":[75,100],"color":"#C0DD97"},
            ],
            "threshold":{"line":{"color":color,"width":3},"thickness":0.75,"value":score}
        },
        title={"text":label,"font":{"size":13,"color":"#666"}},
        domain={"x":[0,1],"y":[0,1]}
    ))
    fig.update_layout(height=220, margin=dict(t=30,b=10,l=20,r=20), paper_bgcolor="rgba(0,0,0,0)")
    return fig

def make_price_chart(history):
    if not history: return None
    df = pd.DataFrame(history)
    mn, mx = df["price"].min()*0.997, df["price"].max()*1.003
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["price"],
        mode="lines+markers",
        line=dict(color="#BA7517",width=2.5),
        marker=dict(size=6,color="#BA7517"),
        fill="tozeroy", fillcolor="rgba(186,117,23,0.07)",
        hovertemplate="$%{y:,.2f}<extra></extra>"
    ))
    fig.update_layout(
        height=260, margin=dict(t=10,b=30,l=60,r=20),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(tickprefix="$",gridcolor="rgba(0,0,0,0.06)",range=[mn,mx]),
        xaxis=dict(gridcolor="rgba(0,0,0,0)"),
        showlegend=False
    )
    return fig

# ── HEADER ────────────────────────────────────────────────────────────────────
st.markdown('<div class="main-header">🥇 Gold Macro Dashboard</div>', unsafe_allow_html=True)

mercado_abierto = is_gold_market_open()
refresh_seg     = get_refresh_seconds()
refresh_min     = refresh_seg // 60

estado_mercado = (
    '<span class="market-open">🟢 Mercado abierto</span>' if mercado_abierto
    else '<span class="market-closed">🔴 Mercado cerrado</span>'
)
st.markdown(
    f'<div class="sub-header">Precio del oro al instante + 4 indicadores que anticipan su movimiento · {estado_mercado} · Refresca cada <b>{refresh_min} min</b></div>',
    unsafe_allow_html=True
)

col_btn, col_ts = st.columns([1,4])
with col_btn:
    if st.button("🔄 Actualizar"):
        st.cache_data.clear()
        st.rerun()
with col_ts:
    st.markdown(
        f"<div style='font-size:12px;color:#aaa;padding-top:8px'>"
        f"Última actualización: {datetime.now().strftime('%H:%M:%S')} · "
        f"Fuente principal: Twelve Data (XAU/USD spot real)</div>",
        unsafe_allow_html=True
    )

st.divider()

# ── CARGA DE DATOS ────────────────────────────────────────────────────────────
with st.spinner("Cargando datos del mercado..."):
    gold_data          = get_gold_price_twelvedata()
    history, hist_src  = get_gold_history_twelvedata(12)
    dxy,  _            = get_fred_value("DTWEXBGS")
    yield10y, _        = get_fred_value("DGS10")
    breakeven, _       = get_fred_value("T10YIE")
    vix,  _            = get_fred_value("VIXCLS")
    if dxy is None:  dxy = get_yahoo_quote("DX-Y.NYB")
    if vix is None:  vix = get_yahoo_quote("%5EVIX")

gold_price = gold_data["price"] if gold_data else None
real_yield = round(yield10y - breakeven, 2) if (yield10y and breakeven) else None

# ── MÉTRICAS ──────────────────────────────────────────────────────────────────
c1,c2,c3,c4 = st.columns(4)

with c1:
    if gold_price:
        delta = f"{gold_data['change']:+.2f} ({gold_data['change_pct']:+.2f}%)" if gold_data.get("change") is not None else None
        st.metric("🥇 Oro XAU/USD", f"${gold_price:,.2f}", delta=delta)
        st.caption(gold_data.get("source","—"))
        if gold_data.get("high") and gold_data.get("low"):
            st.caption(f"H: ${gold_data['high']:,.2f}  ·  L: ${gold_data['low']:,.2f}")
    else:
        st.metric("🥇 Oro XAU/USD", "Sin dato")
        st.caption("Twelve Data no respondió")

with c2:
    if dxy:
        lbl = "Dólar débil ▼" if dxy<100 else "Neutral →" if dxy<104 else "Dólar fuerte ▲"
        st.metric("💵 DXY — Fuerza del dólar", f"{dxy:.2f}", delta=lbl, delta_color="off")
    else:
        st.metric("💵 DXY — Fuerza del dólar", "Sin dato")

with c3:
    if real_yield is not None:
        st.metric("📈 Tasa interés real EE.UU.", f"{real_yield:.2f}%",
                  delta=f"Tasa nominal {yield10y:.2f}% · Inflación esperada {breakeven:.2f}%", delta_color="off")
    elif yield10y:
        st.metric("📈 Tasa interés real EE.UU.", f"{yield10y:.2f}%", delta="Inflación esperada no disponible", delta_color="off")
    else:
        st.metric("📈 Tasa interés real EE.UU.", "Sin dato")

with c4:
    if vix:
        nivel = "⚠ Pánico" if vix>30 else "Elevado" if vix>20 else "Bajo"
        st.metric("😰 VIX — Miedo del mercado", f"{vix:.2f}", delta=nivel, delta_color="off")
    else:
        st.metric("😰 VIX — Miedo del mercado", "Sin dato")

st.divider()

# ── GAUGE + SEÑALES ───────────────────────────────────────────────────────────
col_g, col_s = st.columns([1,1])

with col_g:
    st.markdown("**Indicador de condiciones macro para el oro**")
    st.caption("Puntaje de 0 a 100 que resume qué tan favorables son los indicadores económicos para que el precio del oro suba. 0 = todo en contra · 100 = todo a favor")
    score = calc_score(dxy, real_yield, vix, breakeven)
    st.plotly_chart(make_gauge(score), use_container_width=True, config={"displayModeBar":False})

with col_s:
    st.markdown("**¿Qué dice cada indicador?**")
    st.caption("Cada uno influye en el precio del oro de diferente forma. Verde = favorece subida · Rojo = favorece bajada · Naranja = neutral")
    s1,l1 = get_signal("dxy",        dxy)
    s2,l2 = get_signal("real_yield", real_yield)
    s3,l3 = get_signal("vix",        vix)
    s4,l4 = get_signal("breakeven",  breakeven)
    render_signal("💵 DXY — Fuerza del dólar",    "cuando el dólar sube, el oro baja (y viceversa)",   f"{dxy:.2f}"          if dxy        else None, s1, l1)
    render_signal("📈 Tasa de interés real EE.UU.", "rentabilidad de bonos del Tesoro ya descontando inflación. Si es alta, el oro pierde atractivo", f"{real_yield:.2f}%"  if real_yield else None, s2, l2)
    render_signal("😰 VIX — Miedo en los mercados", "mide el nerviosismo global. Cuando hay pánico, los inversores huyen al oro",                    f"{vix:.2f}"          if vix        else None, s3, l3)
    render_signal("🔥 Inflación esperada EE.UU.",  "qué tan alta espera el mercado que sea la inflación en los próximos 10 años. Más inflación = más demanda de oro como protección", f"{breakeven:.2f}%"   if breakeven  else None, s4, l4)

st.divider()

# ── HISTÓRICO ─────────────────────────────────────────────────────────────────
st.markdown(f"**Precio del oro — últimos 12 días hábiles (USD/oz)** · *{hist_src}*")
fig = make_price_chart(history)
if fig:
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar":False})
else:
    st.info("Sin datos históricos disponibles.")

# ── GUÍA ──────────────────────────────────────────────────────────────────────
with st.expander("📖 ¿Qué significa cada cosa? Guía rápida"):
    st.markdown("""
### 🎯 El Indicador de 0 a 100
Resume en un solo número qué tan favorables están las condiciones macro para que el oro **suba**:
- **0–25 (rojo):** Todo apunta a que el oro puede bajar
- **25–50 (naranja):** Condiciones desfavorables pero no extremas
- **50–75 (verde claro):** Condiciones favorables para el oro
- **75–100 (verde):** Todo apunta a que el oro puede subir

---

### 💵 DXY — Fuerza del dólar estadounidense
Mide qué tan fuerte está el dólar frente a otras monedas.
- **Dólar fuerte (DXY > 104):** el oro tiende a bajar, porque se encarece para compradores de otros países
- **Dólar débil (DXY < 98):** el oro tiende a subir

---

### 📈 Tasa de interés real EE.UU.
Es el rendimiento que pagan los bonos del gobierno de EE.UU., **ya descontando la inflación**.
- Si es alta (> 1.5%): los inversores prefieren bonos seguros que sí pagan intereses → el oro pierde atractivo
- Si es baja o negativa (< 0.5%): el oro se vuelve más atractivo porque "no pagar intereses ya no importa tanto"

---

### 😰 VIX — Miedo del mercado global
Mide el nivel de nerviosismo o pánico en los mercados financieros mundiales.
- **VIX alto (> 25):** hay miedo, los inversores buscan refugio → compran oro → precio sube
- **VIX bajo (< 15):** mercados tranquilos, poca demanda de refugio

---

### 🔥 Inflación esperada EE.UU. (próximos 10 años)
Lo que los mercados esperan que sea la inflación en EE.UU. en la próxima década.
- **Alta (> 2.5%):** el oro es el refugio clásico contra la inflación → precio sube
- **Baja (< 2%):** menos urgencia de protegerse → menor demanda de oro

---

### ⚖️ Pesos del indicador general
| Factor | Peso |
|---|---|
| Fuerza del dólar (DXY)        | 30% |
| Tasa de interés real EE.UU.   | 30% |
| Miedo del mercado (VIX)       | 20% |
| Inflación esperada EE.UU.     | 20% |
    """)

with st.expander("📊 Uso de API (Twelve Data)"):
    try:
        r = requests.get(
            f"https://api.twelvedata.com/api_usage?apikey={TWELVE_DATA_KEY}",
            timeout=8
        )
        if r.status_code == 200:
            u = r.json()
            current = u.get("current_usage", "—")
            limit   = u.get("plan_limit",    800)
            remaining = limit - current if isinstance(current, int) else "—"
            st.markdown(f"""
            - **Plan:** {u.get('plan', 'Basic')}
            - **Usados hoy:** {current} requests
            - **Límite diario:** {limit} requests
            - **Disponibles hoy:** {remaining}
            """)
    except:
        st.caption("No se pudo consultar el uso de la API.")

st.markdown(
    '<div class="footer">Twelve Data (XAU/USD spot) · FRED St. Louis Fed · Yahoo Finance · '
    'No es asesoría de inversión</div>',
    unsafe_allow_html=True
)

# ── Auto-refresh inteligente ──────────────────────────────────────────────────
st.markdown(
    f"<script>setTimeout(()=>window.location.reload(),{refresh_seg * 1000});</script>",
    unsafe_allow_html=True
)
