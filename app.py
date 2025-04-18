# ------------- app.py  (INGRESO + EDICIÓN + KPIs) -------------
import streamlit as st
import pandas as pd, numpy as np
import plotly.express as px, plotly.graph_objects as go
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
import gspread

# ------------------------------------------------------------------
# 1) Configuración inicial
# ------------------------------------------------------------------
st.set_page_config(page_title="Quantitative Journal – Ingreso / KPIs", layout="wide")

scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
creds = Credentials.from_service_account_info(st.secrets["quantitative_journal"], scopes=scope)
gc    = gspread.authorize(creds)
ws    = gc.open_by_key("1D4AlYBD1EClp0gGe0qnxr8NeGMbpSvdOx8yHimQDmbE").worksheet("sheet1")

# Fila‑1 (18 columnas A‑R)
HEADER = [
    "Fecha","Hora","Symbol","Type","Volume","Win/Loss/BE",
    "Gross_USD","Commission","USD","R","Screenshot","Comentarios","Post-Analysis",
    "EOD","ErrorCategory","Resolved","LossTradeReviewURL","IdeaMissedURL"
]

# ------------------------------------------------------------------
# 2) Utilidades
# ------------------------------------------------------------------
def get_all():
    df = pd.DataFrame(ws.get_all_records())
    if not df.empty and "Fecha" in df and "Hora" in df:
        df["Datetime"] = pd.to_datetime(df["Fecha"]+" "+df["Hora"], errors="coerce")
    return df

def calculate_r(net_usd, acct=60000, rpct=0.25):
    risk = acct*(rpct/100)         # 0.25 %
    return round(float(net_usd)/risk, 2) if risk else 0

def append_trade(d):
    ws.append_row([d.get(c,"") for c in HEADER])

def update_row(idx, d):            # idx: 0‑based
    sheet_row = idx+2              # + header
    row_vals  = [d.get(c,"") for c in HEADER]
    ws.update(f"A{sheet_row}:R{sheet_row}", [row_vals])   # 18 columnas

# ------------------------------------------------------------------
df = get_all()
st.title("Quantitative Journal  ·  Registro & Métricas")

# ================================================================
#  SECCIÓN 1 · Registrar un trade
# ================================================================
with st.expander("➕ Registrar trade", expanded=False):
    c1,c2 = st.columns(2)
    with c1:
        fecha  = st.date_input("Fecha").strftime("%Y-%m-%d")
        hora   = st.time_input("Hora").strftime("%H:%M:%S")
        symbol = st.text_input("Symbol", value="EURUSD")
        ttype  = st.selectbox("Type", ["Long","Short"])
        volume = st.number_input("Volume (lotes)", 0.0, step=0.01)
        result = st.selectbox("Resultado", ["Win","Loss","BE"])
    with c2:
        gross  = st.number_input("Gross USD (antes comisión)", 0.0, step=0.01)
        screenshot = st.text_input("Screenshot URL")
        comments   = st.text_area("Comentarios")
        post_an    = st.text_area("Post‑Analysis")
        eod_link   = st.text_input("EOD (link Canva)")
        err_cat    = st.text_input("Error Category")
        resolved   = st.checkbox("¿Error Resuelto?", False)
        ltr_urls   = st.text_input("LossTradeReviewURL(s)  (separa con coma)")
        missed_urls= st.text_input("IdeaMissedURL(s) (opcional)")

    # Comisión y BE
    commission = volume*4.0
    if result == "BE":
        gross = commission          # bruto igual a comisión ⇒ neto 0
    net_usd = gross - commission
    r_value = calculate_r(net_usd)

    if st.button("Agregar Trade"):
        trade = dict(zip(HEADER, [
            fecha,hora,symbol,ttype,volume,result,
            gross,commission,net_usd,r_value,screenshot,comments,post_an,
            eod_link,err_cat,"Yes" if resolved else "No", ltr_urls, missed_urls
        ]))
        append_trade(trade)
        st.success("✔️ Trade agregado")
        df = get_all()

# ================================================================
#  SECCIÓN 2 · KPIs y Visualizaciones
# ================================================================
with st.expander("📊 Métricas / KPIs", expanded=False):
    if df.empty:
        st.info("Aún no hay trades.")
    else:
        # ---------------- cálculo base ----------------
        df["USD"] = pd.to_numeric(df["USD"], errors="coerce")
        total   = len(df)
        wins    = (df["Win/Loss/BE"]=="Win").sum()
        losses  = (df["Win/Loss/BE"]=="Loss").sum()
        be_tr   = (df["Win/Loss/BE"]=="BE").sum()
        win_rate= round(100*wins/total,2) if total else 0
        gross_p = df[df["USD"]>0]["USD"].sum()
        gross_l = df[df["USD"]<0]["USD"].sum()
        net_p   = df["USD"].sum()
        prof_factor = round(abs(gross_p/gross_l),2) if gross_l else 0
        expectancy  = round(df["USD"].mean(),2) if total else 0
        payoff      = round(df[df["USD"]>0]["USD"].mean() / abs(df[df["USD"]<0]["USD"].mean()),2) if losses else 0
        risk_amt    = 60000*0.0025
        expectancy_R= round(expectancy/risk_amt,2) if risk_amt else 0

        # ---------------- KPIs display ----------------
        k1,k2,k3,k4 = st.columns(4)
        k1.metric("Total Trades", total)
        k2.metric("Win Rate", f"{win_rate}%")
        k3.metric("Profit Factor", prof_factor)
        k4.metric("Expectancy", f"{expectancy} USD")

        k5,k6,k7,k8 = st.columns(4)
        k5.metric("Gross Profit", round(gross_p,2))
        k6.metric("Gross Loss", round(gross_l,2))
        k7.metric("Net Profit",  round(net_p,2))
        k8.metric("Payoff ratio", payoff)

        k9,k10 = st.columns(2)
        k9.metric("Expectancy R", expectancy_R)
        # % días verdes
        daily = df.groupby(df["Datetime"].dt.date)["USD"].sum()
        pct_green = round(100*(daily>0).sum()/len(daily),1) if len(daily) else 0
        k10.metric("% días verdes", f"{pct_green}%")

        # Pie Win/Loss/BE
        fig_pie = px.pie(names=["Win","Loss","BE"], values=[wins,losses,be_tr], title="Distribución")
        st.plotly_chart(fig_pie, use_container_width=True)

        # Equity curve + High‑Water Mark
        df = df.sort_values("Datetime") ; df["CumulUSD"] = 60000 + df["USD"].cumsum()
        hwm = df["CumulUSD"].cummax()
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(x=df["Datetime"], y=df["CumulUSD"], mode="lines", name="Equity"))
        fig_eq.add_trace(go.Scatter(x=df["Datetime"], y=hwm, mode="lines", name="High‑Water Mark",
                                    line=dict(dash="dash", color="green")))
        fig_eq.update_layout(title="Evolución de Equity", showlegend=True)
        st.plotly_chart(fig_eq, use_container_width=True)

# ================================================================
#  SECCIÓN 3 · Historial
# ================================================================
with st.expander("📜 Historial de trades", expanded=False):
    st.dataframe(df)

# ================================================================
#  SECCIÓN 4 · Editar / borrar  (ya incluida arriba)
# ================================================================
# ---------------------------------------------------------------
