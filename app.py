import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pytz
import time

TROY_OZ_GRAMS = 31.1035  # 1 onza troy = 31.1035 gramos
TZ_COL = pytz.timezone('America/Bogota')  # UTC-5, sin cambio de horario

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
    now = datetime.now(pytz.utc).astimezone(et)
    wd = now.weekday()  # 0=Lun, 6=Dom
    h  = now.hour + now.minute / 60
    if wd == 5:                          # Sábado: cerrado
        return False
    if wd == 6 and h < 18:              # Domingo antes de 6pm: cerrado
        return False
    if wd == 4 and h >= 17:             # Viernes después de 5pm: cerrado
        return False
    return True


def now_colombia():
    """Hora actual en Colombia (UTC-5, sin horario de verano)."""
    return datetime.now(pytz.utc).astimezone(TZ_COL)

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

# Configuración de periodos del gráfico
CHART_PERIODS = {
    "1D":     {"interval": "5min",  "outputsize": 180, "label": "Hoy — cada 5 min",         "fmt": "%H:%M",  "ttl": 60},
    "5D":     {"interval": "2h",    "outputsize": 60,  "label": "5 días — cada 2 horas",     "fmt": "%m/%d %H:%M", "ttl": 120},
    "1M":     {"interval": "4h",    "outputsize": 180, "label": "30 días — cada 4 horas",    "fmt": "%m/%d",  "ttl": 300},
    "3M":     {"interval": "1day",  "outputsize": 90,  "label": "3 meses — cada día",        "fmt": "%m/%d",  "ttl": 300},
    "YTD":    {"interval": "1day",  "outputsize": 365, "label": "Año en curso — cada día",   "fmt": "%m/%d",  "ttl": 300},
}

@st.cache_data(ttl=60)
def get_gold_history_period(period="3M"):
    cfg = CHART_PERIODS.get(period, CHART_PERIODS["3M"])
    interval   = cfg["interval"]
    outputsize = cfg["outputsize"]
    fmt        = cfg["fmt"]
    try:
        r = requests.get(
            f"https://api.twelvedata.com/time_series?symbol=XAU/USD"
            f"&interval={interval}&outputsize={outputsize}&apikey={TWELVE_DATA_KEY}",
            timeout=15
        )
        if r.status_code == 200:
            d = r.json()
            if d.get("values"):
                results = []
                # Para YTD filtrar solo desde 1 enero del año actual
                year_start = datetime(datetime.now().year, 1, 1)
                for v in reversed(d["values"]):
                    try:
                        # Twelve Data devuelve "YYYY-MM-DD" para 1day, "YYYY-MM-DD HH:MM:SS" para intraday
                        raw = v["datetime"]
                        if " " in raw:
                            # Intraday: Twelve Data devuelve hora en UTC → convertir a Colombia
                            dt_utc = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=pytz.utc)
                            dt = dt_utc.astimezone(TZ_COL)
                        else:
                            dt = datetime.strptime(raw, "%Y-%m-%d")
                        if period == "YTD" and dt.replace(tzinfo=None) < year_start:
                            continue
                        results.append({"date": dt.strftime(fmt), "price": float(v["close"]), "dt": dt})
                    except:
                        pass
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
@st.cache_data(ttl=120)
def get_brent_price():
    """Precio del Brent — intenta Twelve Data luego Yahoo Finance."""
    # Twelve Data
    try:
        r = requests.get(
            f"https://api.twelvedata.com/price?symbol=BRENT/USD&apikey={TWELVE_DATA_KEY}",
            timeout=10
        )
        if r.status_code == 200:
            d = r.json()
            if d.get("price"):
                price = float(d["price"])
                r2 = requests.get(
                    f"https://api.twelvedata.com/quote?symbol=BRENT/USD&apikey={TWELVE_DATA_KEY}",
                    timeout=10
                )
                change, change_pct = None, None
                if r2.status_code == 200:
                    q = r2.json()
                    if not q.get("code"):
                        change     = float(q.get("change", 0) or 0)
                        change_pct = float(q.get("percent_change", 0) or 0)
                return {"price": price, "change": change, "change_pct": change_pct, "source": "Twelve Data"}
    except:
        pass
    # Yahoo Finance fallback
    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/BZ%3DF?interval=1d&range=2d",
            headers=HEADERS, timeout=10
        )
        if r.status_code == 200:
            meta  = r.json()["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice")
            prev  = meta.get("chartPreviousClose")
            if price:
                ch  = round(price - prev, 2) if prev else None
                chp = round(ch / prev * 100, 2) if (ch and prev) else None
                return {"price": price, "change": ch, "change_pct": chp, "source": "Yahoo (BZ=F)"}
    except:
        pass
    return None

@st.cache_data(ttl=120)
def get_usdcop():
    """Tasa de cambio USD/COP desde Yahoo Finance."""
    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/USDCOP%3DX?interval=1d&range=2d",
            headers=HEADERS, timeout=10
        )
        if r.status_code == 200:
            meta  = r.json()["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice")
            prev  = meta.get("chartPreviousClose")
            if price:
                ch  = round(price - prev, 2) if prev else None
                chp = round(ch / prev * 100, 2) if (ch and prev) else None
                return {"price": price, "change": ch, "change_pct": chp}
    except:
        pass
    return None

def get_brent_gold_correlation(brent_price, gold_price):
    """Señal simple de correlación basada en movimiento del día."""
    if brent_price is None or gold_price is None:
        return "neutral", "Sin datos suficientes"
    brent_ch = brent_price.get("change_pct") or 0
    gold_ch  = gold_price.get("change_pct") or 0
    if abs(brent_ch) < 0.1 and abs(gold_ch) < 0.1:
        return "neutral", "Ambos estables hoy"
    if brent_ch > 0.2 and gold_ch < -0.1:
        return "bearish", "Brent sube · Oro cae → correlación inversa activa"
    if brent_ch < -0.2 and gold_ch > 0.1:
        return "bullish", "Brent cae · Oro sube → correlación inversa activa"
    if brent_ch > 0.2 and gold_ch > 0.1:
        return "neutral", "Ambos suben → posible pánico geopolítico"
    if brent_ch < -0.2 and gold_ch < -0.1:
        return "neutral", "Ambos caen → presión general de mercado"
    return "neutral", "Sin correlación clara hoy"



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
        f"Última actualización: {now_colombia().strftime('%H:%M:%S')} (hora Colombia) · "
        f"Fuente principal: Twelve Data (XAU/USD spot real)</div>",
        unsafe_allow_html=True
    )

st.divider()

# ── CARGA DE DATOS ────────────────────────────────────────────────────────────
with st.spinner("Cargando datos del mercado..."):
    gold_data          = get_gold_price_twelvedata()
    # DXY: Yahoo Finance primero (tiempo real), FRED como fallback
    dxy = get_yahoo_quote("DX-Y.NYB")
    if dxy is None: dxy, _ = get_fred_value("DTWEXBGS")

    # Yield 10Y nominal: Yahoo Finance ^TNX (tiempo real), FRED como fallback
    yield10y = get_yahoo_quote("%5ETNX")
    if yield10y is None: yield10y, _ = get_fred_value("DGS10")
    else: yield10y = round(yield10y, 2)

    # VIX: Yahoo Finance primero (tiempo real), FRED como fallback
    vix = get_yahoo_quote("%5EVIX")
    if vix is None: vix, _ = get_fred_value("VIXCLS")

    # Breakeven inflación: calculado como Yield nominal (^TNX) - Yield real TIPS (DFII10)
    # T10YIE de FRED está congelado desde abril 2026, por eso lo calculamos manualmente
    # DFII10 (yield real TIPS) sí está actualizado en FRED
    tips_real, tips_date = get_fred_value("DFII10")
    if yield10y is not None and tips_real is not None:
        breakeven = round(yield10y - tips_real, 2)
        be_date   = tips_date
    else:
        # Fallback: intentar T10YIE directo de FRED (aunque esté desactualizado)
        breakeven, be_date = get_fred_value("T10YIE")
    brent_data = get_brent_price()
    usdcop_data = get_usdcop()

gold_price  = gold_data["price"]    if gold_data    else None
# Yield real: usamos DFII10 directamente (es el yield real TIPS por definición)
# Si no está disponible, calculamos como yield nominal - breakeven
real_yield = round(tips_real, 2) if tips_real is not None else (round(yield10y - breakeven, 2) if (yield10y and breakeven) else None)
brent_price = brent_data["price"]  if brent_data  else None
usdcop      = usdcop_data["price"] if usdcop_data else None
gold_usd_gram = round(gold_price / TROY_OZ_GRAMS, 2) if gold_price else None
gold_cop_gram = round((gold_price * usdcop) / TROY_OZ_GRAMS) if (gold_price and usdcop) else None

# ── MÉTRICAS ──────────────────────────────────────────────────────────────────
c1,c2,c3,c4,c5,c6 = st.columns(6)

with c1:
    if gold_price:
        delta = f"{gold_data['change']:+.2f} ({gold_data['change_pct']:+.2f}%)" if gold_data.get("change") is not None else None
        st.metric("🥇 Oro XAU/USD", f"${gold_price:,.2f}", delta=delta)
        st.caption(gold_data.get("source","—"))
        if gold_data.get("high") and gold_data.get("low"):
            st.caption(f"H: ${gold_data['high']:,.2f}  ·  L: ${gold_data['low']:,.2f}")
        if gold_usd_gram:
            st.caption(f"📌 Por gramo: ${gold_usd_gram:,.2f} USD/g")
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
                  delta=f"Nominal {yield10y:.2f}% · BE {breakeven:.2f}%", delta_color="off")
        if be_date:
            st.caption(f"Breakeven dato: {be_date}")
    elif yield10y:
        st.metric("📈 Tasa interés real EE.UU.", f"{yield10y:.2f}%", delta="Breakeven no disponible", delta_color="off")
    else:
        st.metric("📈 Tasa interés real EE.UU.", "Sin dato")

with c4:
    if vix:
        nivel = "⚠ Pánico" if vix>30 else "Elevado" if vix>20 else "Bajo"
        st.metric("😰 VIX — Miedo del mercado", f"{vix:.2f}", delta=nivel, delta_color="off")
    else:
        st.metric("😰 VIX — Miedo del mercado", "Sin dato")

with c5:
    if brent_price:
        b_ch  = brent_data.get("change")
        b_chp = brent_data.get("change_pct")
        delta_b = f"{b_ch:+.2f} ({b_chp:+.2f}%)" if (b_ch is not None and b_chp is not None) else None
        st.metric("🛢 Brent — Petróleo", f"${brent_price:,.2f}", delta=delta_b)
        st.caption("USD por barril")
    else:
        st.metric("🛢 Brent — Petróleo", "Sin dato")

with c6:
    if usdcop:
        c_ch  = usdcop_data.get("change")
        c_chp = usdcop_data.get("change_pct")
        delta_cop = f"{c_ch:+.2f} ({c_chp:+.2f}%)" if (c_ch is not None and c_chp is not None) else None
        st.metric("🇨🇴 USD/COP", f"{usdcop:,.1f}", delta=delta_cop)
        if gold_cop_gram:
            st.caption(f"📌 Oro hoy: {gold_cop_gram:,} COP/g")
    else:
        st.metric("🇨🇴 USD/COP", "Sin dato")

st.divider()

# ── GAUGE + SEÑALES ───────────────────────────────────────────────────────────
col_g, col_s = st.columns([1,1])

with col_g:
    st.markdown("**Indicador de condiciones macro para el oro**")
    st.caption("Puntaje de 0 a 100 que resume qué tan favorables son los indicadores económicos para que el precio del oro suba. 0 = todo en contra · 100 = todo a favor")
    score = calc_score(dxy, real_yield, vix, breakeven)
    st.plotly_chart(make_gauge(score), use_container_width=True, config={"displayModeBar":False})

    st.markdown("""
<div style="font-size:12px;line-height:2;margin-top:-8px;">
<span style="color:#A32D2D">&#9632; <b>0&#8211;25:</b> Todo apunta a bajada del oro</span><br>
<span style="color:#C87800">&#9632; <b>25&#8211;50:</b> Condiciones desfavorables</span><br>
<span style="color:#5a8a00">&#9632; <b>50&#8211;75:</b> Condiciones favorables</span><br>
<span style="color:#3B6D11">&#9632; <b>75&#8211;100:</b> Todo apunta a subida del oro</span>
</div>
""", unsafe_allow_html=True)

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
    be_label = f"{breakeven:.2f}%" if breakeven else None
    be_date_txt = f" (dato: {be_date})" if (breakeven and be_date) else ""
    render_signal("🔥 Inflación esperada EE.UU.",  f"qué tan alta espera el mercado que sea la inflación en los próximos 10 años. Más inflación = más demanda de oro como protección{be_date_txt}", be_label, s4, l4)

    st.markdown("---")
    st.markdown("**🛢 Petróleo Brent vs Oro**")
    st.caption("Relación de comportamiento entre ambos activos en el día de hoy")
    bcor_sig, bcor_label = get_brent_gold_correlation(brent_data, gold_data)
    brent_val = f"${brent_price:,.2f}/barril" if brent_price else None
    render_signal("🛢 Brent — Crudo del Mar del Norte", "precio referencia mundial del petróleo. Con tensión en Medio Oriente, suele moverse inverso al oro", brent_val, bcor_sig, bcor_label)

st.divider()

# ── HISTÓRICO CON SELECTOR DE PERIODO ────────────────────────────────────────
st.markdown("**Precio del oro (USD/oz) — selecciona el período**")

# Botones de periodo
col_p1, col_p2, col_p3, col_p4, col_p5, col_rest = st.columns([1,1,1,1,1,5])
period_map = {"1D": col_p1, "5D": col_p2, "1M": col_p3, "3M": col_p4, "YTD": col_p5}

if "chart_period" not in st.session_state:
    st.session_state.chart_period = "3M"

for period, col in period_map.items():
    with col:
        label = period
        if st.button(label, key=f"btn_{period}",
                     type="primary" if st.session_state.chart_period == period else "secondary",
                     use_container_width=True):
            st.session_state.chart_period = period
            st.rerun()

selected = st.session_state.chart_period
cfg = CHART_PERIODS[selected]

with st.spinner(f"Cargando {cfg['label']}..."):
    history, hist_src = get_gold_history_period(selected)

st.caption(f"{cfg['label']} · Fuente: {hist_src}")

fig = make_price_chart(history)
if fig:
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
else:
    st.info("Sin datos para este período. Intenta con otro rango o espera unos segundos.")

# ── GUÍA ──────────────────────────────────────────────────────────────────────
with st.expander("📖 ¿Qué significa cada cosa? Guía rápida"):
    st.markdown("""
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

### 🛢 Brent — Petróleo crudo
Precio de referencia mundial del crudo, producido en el Mar del Norte.
- En contexto de tensión en Medio Oriente / Estrecho de Ormuz: cuando el Brent sube por riesgo geopolítico energético (no financiero), el oro tiende a bajar — los capitales rotan hacia energía
- Cuando hay pánico financiero real: ambos pueden subir juntos como activos de crisis

### 🇨🇴 USD/COP — Dólar vs Peso colombiano
Cuántos pesos colombianos vale 1 dólar estadounidense.
- Si el dólar sube frente al peso: el oro en COP se encarece más de lo que sube en USD
- Abajo del precio aparece el **valor de la onza de oro en pesos** — calculado automáticamente

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
