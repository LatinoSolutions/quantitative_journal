import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from google.oauth2.service_account import Credentials
import gspread

# ------------------------------------------------------
# 1) Configuración general de la página de Streamlit
# ------------------------------------------------------
st.set_page_config(
    page_title="Quantitative Journal - READ ONLY",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ------------------------------------------------------
# 2) Conexión a Google Sheets
# ------------------------------------------------------
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

creds_dict = st.secrets["quantitative_journal"]
credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
gc = gspread.authorize(credentials)

# Ajusta a tu Spreadsheet Key y hoja
SPREADSHEET_KEY = "1D4AlYBD1EClp0gGe0qnxr8NeGMbpSvdOx8yHimQDmbE"
sh = gc.open_by_key(SPREADSHEET_KEY)
worksheet = sh.worksheet("sheet1")

# ------------------------------------------------------
# 3) Funciones auxiliares (solo lectura)
# ------------------------------------------------------
def get_all_trades() -> pd.DataFrame:
    """
    Lee todos los registros de la hoja y los retorna como DataFrame.
    """
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)
    if not df.empty and "Fecha" in df.columns and "Hora" in df.columns:
        df["Datetime"] = pd.to_datetime(df["Fecha"] + " " + df["Hora"], errors="coerce")
    return df

# ------------------------------------------------------
# 4) Lectura del DF y Layout
# ------------------------------------------------------
df = get_all_trades()
st.title("Quantitative Journal - Solo Lectura")

if df.empty:
    st.warning("Aún no hay datos registrados.")
else:
    # Convertir a tipo numérico las columnas relevantes si existen
    for col_name in ["Volume","Gross_USD","Commission","USD","R"]:
        if col_name in df.columns:
            df[col_name] = pd.to_numeric(df[col_name], errors="coerce")

    # ==============================
    # SECCIÓN 1: Feature Engineering & Métricas
    # ==============================
    with st.expander("1. Métricas y Visualizaciones", expanded=True):
        total_trades = len(df)
        wins = len(df[df["Win/Loss/BE"] == "Win"])
        losses = len(df[df["Win/Loss/BE"] == "Loss"])
        be = len(df[df["Win/Loss/BE"] == "BE"])
        win_rate = round((wins / total_trades) * 100, 2) if total_trades > 0 else 0

        gross_profit = df[df["USD"] > 0]["USD"].sum()
        gross_loss = df[df["USD"] < 0]["USD"].sum()
        net_profit = df["USD"].sum()

        profit_factor = 0
        if gross_loss != 0:
            profit_factor = round(abs(gross_profit / gross_loss), 2)

        best_profit = df["USD"].max()
        worst_loss = df["USD"].min()
        avg_profit = df[df["USD"] > 0]["USD"].mean() if wins > 0 else 0
        avg_loss = df[df["USD"] < 0]["USD"].mean() if losses > 0 else 0
        expectancy = round(df["USD"].mean(), 2) if total_trades > 0 else 0

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Trades", total_trades)
        col2.metric("Win Rate", f"{win_rate}%")
        col3.metric("Profit Factor", profit_factor)
        col4.metric("Expectancy", f"{expectancy} USD")

        col5, col6, col7, col8 = st.columns(4)
        col5.metric("Gross Profit (neto)", round(gross_profit,2))
        col6.metric("Gross Loss (neto)", round(gross_loss,2))
        col7.metric("Net Profit", round(net_profit,2))
        col8.write(" ")

        # Curva de equity
        initial_capital = 60000
        df = df.sort_values("Datetime").reset_index(drop=True)
        df["Cumulative_USD"] = initial_capital + df["USD"].cumsum()
        current_equity = df["Cumulative_USD"].iloc[-1]
        pct_change = ((current_equity - initial_capital)/initial_capital)*100

        col9, col10 = st.columns(2)
        col9.metric("Equity actual", f"{round(current_equity,2)} USD", f"{round(pct_change,2)}% vs. inicio")

        # Pie Chart Win/Loss/BE
        fig_pie = px.pie(
            names=["Win","Loss","BE"],
            values=[wins, losses, be],
            title="Distribución Win / Loss / BE"
        )
        st.plotly_chart(fig_pie, use_container_width=True)

        # Evolución de la cuenta
        fig_line = px.line(
            df,
            x="Datetime",
            y="Cumulative_USD",
            title="Evolución de la cuenta (USD Neto)"
        )
        st.plotly_chart(fig_line, use_container_width=True)

    # ==============================
    # SECCIÓN 2: Historial de trades
    # ==============================
    with st.expander("2. Historial de trades (Solo Lectura)", expanded=False):
        st.dataframe(df, use_container_width=True)

st.write("Versión de Solo Lectura - No se pueden agregar ni editar trades aquí.")
