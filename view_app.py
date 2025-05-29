# ------------------ app_gallery.py ------------------
import streamlit as st, pandas as pd
from google.oauth2.service_account import Credentials
import gspread

st.set_page_config("Quantitative Journal – Galería", layout="wide")

# ---------- conexión ----------
creds = Credentials.from_service_account_info(
    st.secrets["quantitative_journal"],
    scopes=["https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"])
ws = gspread.authorize(creds)\
        .open_by_key("1D4AlYBD1EClp0gGe0qnxr8NeGMbpSvdOx8yHimQDmbE")\
        .worksheet("sheet1")
df = pd.DataFrame(ws.get_all_records())
if df.empty:
    st.warning("No hay datos.")
    st.stop()

# ---------- Filtros barra lateral ----------
st.sidebar.header("Filtros")
res_filter = st.sidebar.multiselect(
    "Resultado", ["Win","Loss","BE"], default=["Win","Loss","BE"])
start, end = st.sidebar.date_input(
    "Rango fechas", [], key="date", help="Opcional: filtra por fecha")
only_pending = st.sidebar.checkbox("Sólo Loss sin Resolver")

# aplicar filtros
df["Fecha_dt"] = pd.to_datetime(df["Fecha"])
if start and end:
    df = df[(df["Fecha_dt"]>=pd.to_datetime(start)) &
            (df["Fecha_dt"]<=pd.to_datetime(end))]
df = df[df["Win/Loss/BE"].isin(res_filter)]
if only_pending:
    df = df[(df["Win/Loss/BE"]=="Loss") & (df["Resolved"]!="Yes")]

st.title("🖼️ Galería de Trades")

# ---------- Tarjetas ----------
PER_PAGE = 20
page = st.sidebar.number_input("Página", 1, max(1,int(len(df)/PER_PAGE)+1))
start_i = (page-1)*PER_PAGE; end_i = start_i+PER_PAGE
sub = df.sort_values("Datetime", ascending=False).iloc[start_i:end_i]

def mini(card):
    r = card["R"]; usd = card["USD"]
    st.image(card["LossTradeReviewURL"] or card["Screenshot"], width=260,
             caption=f"{card['Fecha']}  |  {card['Win/Loss/BE']}  |  {usd:+,.2f} USD  |  {r:+.2f} R")
    with st.expander("Detalle"):
        for col in ["Symbol","Type","Volume","ErrorCategory","Comentarios",
                    "Post-Analysis","EOD","Resolved"]:
            st.write(f"**{col}**: {card[col]}")
        if card["Screenshot"]:
            st.markdown(f"[Abrir Screenshot]({card['Screenshot']})")
        if card["LossTradeReviewURL"]:
            st.markdown(f"[Abrir Review]({card['LossTradeReviewURL']})")

cols = st.columns(4)
for i,(idx,row) in enumerate(sub.iterrows()):
    with cols[i%4]:
        mini(row)
