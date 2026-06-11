# 📋 Resumen del Proyecto — Gold Macro Dashboard
**Fecha:** Junio 2026  
**Desarrollado por:** Hector Ivan Aristizabal — con asistencia de Claude (Anthropic)

---

## 🎯 Objetivo del proyecto

Construir un dashboard web accesible desde cualquier navegador (sin instalar nada) para monitorear el precio del oro XAU/USD y los indicadores macroeconómicos que permiten anticipar su comportamiento. Diseñado para ser compartido con su hermano.

---

## 🌐 Plataforma de publicación

- **Streamlit Cloud:** [share.streamlit.io](https://share.streamlit.io)
- **Repositorio GitHub:** `gold-dashboard` (cuenta de Hector)
- **Archivo principal:** `app.py`
- **Auto-redeploy:** cada vez que se actualiza `app.py` en GitHub, Streamlit Cloud lo despliega automáticamente en ~1 minuto

---

## 📁 Archivos del proyecto

```
gold-dashboard/
├── app.py                  ← Aplicación principal (único archivo a editar)
├── requirements.txt        ← Dependencias Python
├── .gitignore              ← Excluye secrets del repositorio
└── secrets_example.toml    ← Referencia (NO subir a GitHub)
```

**requirements.txt:**
```
streamlit>=1.32.0
requests>=2.31.0
pandas>=2.0.0
plotly>=5.18.0
pytz>=2024.1
```

---

## 🔑 API Keys configuradas

Se configuran en **Streamlit Cloud → Settings → Secrets** (NO en el código):

```toml
TWELVE_DATA_KEY = "f589353e36df44e498cbb5e847f30015"
FRED_API_KEY    = "tu_key_de_fred"   # obtenida en fred.stlouisfed.org
```

### Fuentes de datos por indicador

| Indicador | Fuente | Plan | Límite |
|---|---|---|---|
| Oro XAU/USD spot | Twelve Data | Basic (gratis) | 800 req/día |
| Histórico oro | Twelve Data | Basic (gratis) | incluido |
| Petróleo Brent | Twelve Data + Yahoo Finance fallback | Basic | incluido |
| DXY, Yield 10Y, Breakeven, VIX | FRED (St. Louis Fed) | Gratis con key | sin límite |
| USD/COP | Yahoo Finance | Gratis | sin límite |

**Próximo plan si se necesitan más consultas:** Twelve Data **Grow** a **$29/mes** — elimina el límite diario de 800 requests y permite refresco cada 60 segundos.

---

## 📊 Indicadores del dashboard

### Fila de métricas (6 columnas)

| Métrica | Descripción |
|---|---|
| 🥇 Oro XAU/USD | Precio spot en USD/oz + cambio del día + precio por gramo USD |
| 💵 DXY — Fuerza del dólar | Índice dólar vs cesta de monedas. Correlación inversa con el oro |
| 📈 Tasa de interés real EE.UU. | Yield 10Y nominal menos breakeven inflación. Inversa con el oro |
| 😰 VIX — Miedo del mercado | Volatilidad implícita S&P500. Alta = refugio en oro |
| 🛢 Brent — Petróleo | Precio barril en USD. Correlación variable con el oro |
| 🇨🇴 USD/COP | Precio del dólar en pesos + **precio del oro en COP por gramo** |

### Indicador macro 0–100 (gauge)
- Combina los 4 indicadores principales con pesos: **DXY 30% · Yield real 30% · VIX 20% · Inflación 20%**
- 0–25: sesgo bajista fuerte · 25–50: desfavorable · 50–75: favorable · 75–100: sesgo alcista fuerte
- Leyenda de colores visible directamente debajo del gauge

### Señales por indicador
- Cada indicador muestra su valor + descripción en lenguaje simple + señal (verde/rojo/naranja)
- Incluye señal de **correlación dinámica Brent vs Oro** del día actual

### Gráfico histórico con selector de períodos
| Botón | Intervalo | Ventana |
|---|---|---|
| 1D | 5 minutos | Últimas ~15 horas |
| 5D | 2 horas | Últimos 5 días |
| 1M | 4 horas | Últimos 30 días |
| 3M | 1 día | Últimos 90 días ← **default** |
| YTD | 1 día | Desde 1 enero del año |

---

## ⚙️ Comportamiento técnico

### Optimización de requests (800/día)
- **Mercado abierto** (Dom 6pm ET → Vie 5pm ET): refresca cada **2 minutos**
- **Mercado cerrado** (fines de semana y fuera de horario): refresca cada **30 minutos**
- Con este esquema los 800 requests/día alcanzan cómodamente

### Timezone
- Toda hora mostrada en el dashboard usa **hora Colombia (UTC-5, America/Bogota)**
- Sin cambio de horario de verano
- Los timestamps intraday de Twelve Data (UTC) se convierten automáticamente

### Precio del oro en gramos
- **1 onza troy = 31.1035 gramos** (constante exacta usada en el código)
- `USD/g = precio_onza / 31.1035`
- `COP/g = (precio_onza × USDCOP) / 31.1035`

### Fuentes en cascada (fallbacks)
El precio del oro intenta en orden:
1. Twelve Data XAU/USD (principal)
2. metals.live (fallback)
3. Yahoo Finance GC=F ajustado (fallback)
4. Frankfurter API (último recurso)

---

## 📈 Contexto de los indicadores — Guía de interpretación

### ¿Por qué estos indicadores predicen el oro?

| Indicador | Relación | Umbral alcista | Umbral bajista |
|---|---|---|---|
| DXY | Inversa (-0.5 a -0.8) | < 98 | > 104 |
| Yield real 10Y | Inversa fuerte | < 0.5% | > 1.5% |
| VIX | Directa en pánico | > 25 | < 15 |
| Breakeven inflación | Directa | > 2.5% | < 2.0% |
| Brent petróleo | Variable según contexto | — | — |

**Nota Brent:** en contexto de tensión Medio Oriente/Estrecho de Ormuz la correlación suele ser **inversa** (Brent sube → oro baja, capital rota a energía). En pánico financiero sistémico ambos pueden subir juntos.

**Diferencia de precio Twelve Data vs TradingView TVC:GOLD:** normal, diferencia de $1–2 es aceptable. Ambos son precio spot legítimo de fuentes distintas. La diferencia con GC=F (futuros) es de ~$35 por el "basis" (costo de acarreo hasta vencimiento del contrato).

---

## 🚀 Cómo actualizar el dashboard

1. Editar `app.py` localmente
2. Subir a GitHub (reemplazar el archivo)
3. Streamlit Cloud detecta el cambio y redespliega en ~1 minuto automáticamente
4. No es necesario tocar nada en Streamlit Cloud

---

## 🔮 Mejoras pendientes / ideas para próximas sesiones

- [ ] Agregar alerta por email o Telegram cuando el indicador macro supere cierto umbral
- [ ] Agregar gráfico comparativo Oro vs Brent (correlación visual)
- [ ] Agregar compras de bancos centrales (World Gold Council — datos trimestrales)
- [ ] Considerar subir a Twelve Data Grow ($29/mes) para refresco de 60 segundos
- [ ] Panel de noticias recientes relacionadas con el oro

---

## 📦 Versiones del archivo app.py

| Versión | Cambio principal |
|---|---|
| v1 | Dashboard inicial (Artifact en Claude, con CORS) |
| v2 | Streamlit Cloud — múltiples fuentes con fallback |
| v3 | Cambio a XAU=X spot (causó sin dato) |
| v4 | GC=F con ajuste de basis -$35 |
| v5 | **Twelve Data como fuente principal XAU/USD spot** |
| v6 | Textos en lenguaje simple para el hermano |
| v7 | Agregado Brent y USD/COP con precio en COP/g |
| v7fix | Corrección error None en formato de cambios |
| v8 | Precio por gramo en USD y COP (÷ 31.1035) |
| v9 | Leyenda del gauge movida debajo del gráfico |
| v10 | Gráfico histórico con botones 1D/5D/1M/3M/YTD |
| **v11** | **Timezone Colombia en hora y gráfico intraday** ← actual |
