# -------------------  app_experimental.py  -------------------
import streamlit as st, pandas as pd, numpy as np
import plotly.express as px, plotly.graph_objects as go
from google.oauth2.service_account import Credentials
import gspread

# -------------------------------------------------------------
# CONFIGURACIÓN
# -------------------------------------------------------------
st.set_page_config(page_title="Quantitative Journal – Experimental",
                   layout="wide", initial_sidebar_state="expanded")

creds = Credentials.from_service_account_info(
            st.secrets["quantitative_journal"],
            scopes=["https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"])
ws = gspread.authorize(creds)\
        .open_by_key("1D4AlYBD1EClp0gGe0qnxr8NeGMbpSvdOx8yHimQDmbE")\
        .worksheet("sheet1")

def get_all():
    df = pd.DataFrame(ws.get_all_records())
    if not df.empty:
        df["Datetime"] = pd.to_datetime(df["Fecha"]+" "+df["Hora"], errors="coerce")
    return df

def drawdown(eq): return eq.cummax() - eq

# -------------------------------------------------------------
df = get_all()
st.title("Quantitative Journal – Experimental Features")

if df.empty:
    st.warning("Hoja vacía.")
    st.stop()

# ------- filtros -------
df_real = df[df["IsIdeaOnly"] != "Yes"].copy()
df_real[["USD","Volume"]] = df_real[["USD","Volume"]].apply(
                                pd.to_numeric, errors="coerce")
df = df.sort_values("Datetime").reset_index(drop=True)
initial_cap = 60000
df_real = df_real.sort_values("Datetime")
df_real["CumulUSD"] = initial_cap + df_real["USD"].cumsum()

# ============================================================
# 1) Métricas avanzadas (consecutivos, DD, Sharpe/Sortino) — sólo trades reales
# ============================================================
with st.expander("1) Métricas de rendimiento avanzado", expanded=False):
    # consecutivos
    cw=cl=mxw=mxl=0
    for res in df_real["Win/Loss/BE"]:
        if res=="Win": cw+=1; mxw=max(mxw,cw); cl=0
        elif res=="Loss": cl+=1; mxl=max(mxl,cl); cw=0
        else: cw=cl=0
    c1,c2 = st.columns(2); c1.metric("Max Wins",mxw); c2.metric("Max Losses",mxl)

    dd = drawdown(df_real["CumulUSD"])
    st.write(f"**Máx DD:** {round(dd.max(),2)} USD / "
             f"{round(100*dd.max()/initial_cap,2)} %")
    st.plotly_chart(
        go.Figure(go.Scatter(x=df_real["Datetime"],y=dd,mode="lines",
                             line=dict(color="red"))).update_layout(
            title="Drawdown over time"), use_container_width=True)

# ============================================================
# 2) Resúmenes semanales / mensuales (trades reales)
# ============================================================
with st.expander("2) Resúmenes semanales / mensuales", expanded=False):
    df_real["WeekTag"]  = df_real["Datetime"].dt.isocalendar().year.astype(str)+\
                          "-W"+df_real["Datetime"].dt.isocalendar().week.astype(str)
    weekly = df_real.groupby("WeekTag").agg(Trades=("USD","count"),
                                            NetPNL=("USD","sum")).reset_index()
    st.dataframe(weekly); st.plotly_chart(px.bar(weekly,x="WeekTag",y="NetPNL",
                    title="PNL semanal"), use_container_width=True)

    df_real["MonthTag"] = df_real["Datetime"].dt.strftime("%Y-%m")
    monthly = df_real.groupby("MonthTag").agg(Trades=("USD","count"),
                                              NetPNL=("USD","sum")).reset_index()
    st.dataframe(monthly); st.plotly_chart(px.bar(monthly,x="MonthTag",y="NetPNL",
                    title="PNL mensual"), use_container_width=True)

# ============================================================
# 3) Calendario / timeline (trades reales)
# ============================================================
with st.expander("3) Calendario / Timeline", expanded=False):
    daily = df_real.groupby(df_real["Datetime"].dt.date)\
                   .agg(Trades=("USD","count"),NetPNL=("USD","sum")).reset_index()\
                   .rename(columns={"Datetime":"DateOnly"})
    st.plotly_chart(px.bar(daily,x="DateOnly",y="Trades",title="# Trades por día"),
                    use_container_width=True)
    st.plotly_chart(px.bar(daily,x="DateOnly",y="NetPNL",title="PNL diario"),
                    use_container_width=True)

# ============================================================
# 4) Análisis por Symbol / Hora (trades reales)
# ============================================================
with st.expander("4) Análisis por Symbol / Hora", expanded=False):
    st.plotly_chart(px.bar(df_real.groupby("Symbol")["USD"].sum().reset_index(),
                           x="Symbol",y="USD",title="PNL por símbolo",
                           color="Symbol"), use_container_width=True)
    df_real["Hour"] = pd.to_datetime(df_real["Hora"],format="%H:%M:%S",
                                     errors="coerce").dt.hour
    st.plotly_chart(px.bar(df_real.groupby("Hour")["USD"].sum().reset_index(),
                           x="Hour",y="USD",title="PNL por hora"),
                    use_container_width=True)

# ============================================================
# 5) Post‑Analysis · Categorías de error (trades reales)
# ============================================================
with st.expander("5) Post‑Analysis · Categorías de error", expanded=False):
    if "ErrorCategory" in df_real:
        loss_cat = df_real[df_real["USD"]<0]\
                   .groupby("ErrorCategory")["USD"].sum().reset_index()\
                   .rename(columns={"USD":"LossSum"})
        st.dataframe(loss_cat)
        st.plotly_chart(px.bar(loss_cat,x="ErrorCategory",y="LossSum",
                               title="Pérdidas por categoría",
                               color="ErrorCategory"), use_container_width=True)

# ============================================================
# 6) Loss Trade Reviews – galería (pérdidas reales)
# ============================================================
with st.expander("6) Loss Trade Reviews (galería)", expanded=False):
    ltr = df[(df["IsIdeaOnly"]!="Yes") & (df["Win/Loss/BE"]=="Loss") &
             (df["LossTradeReviewURL"].str.strip()!="")]
    if ltr.empty:
        st.info("No hay Loss Trade Reviews.")
    else:
        for _, row in ltr.sort_values("Datetime",ascending=False).iterrows():
            st.write(f"**{row['Fecha']} {row['Hora']} – {row['Symbol']}**")
            st.write(f"Categoría: {row.get('ErrorCategory','–')}   |  "
                     f"Resolved: {row.get('Resolved','No')}")
            urls = [u.strip() for u in row["LossTradeReviewURL"].split(",")]
            cols = st.columns(min(3,len(urls)))
            for i,url in enumerate(urls):
                if url:
                    with cols[i%len(cols)]:
                        st.markdown(f'<a href="{url}" target="_blank">'
                                    f'<img src="{url}" width="880" '
                                    'style="margin:3px;border:1px solid #ccc;"></a>',
                                    unsafe_allow_html=True)
            st.write("---")

# ============================================================
# 7) Miedito Trades (ideas no ejecutadas)
# ============================================================
with st.expander("7) Miedito Trades", expanded=False):
    mid = df[df["IsIdeaOnly"]=="Yes"].copy()
    if mid.empty:
        st.info("No hay ideas no ejecutadas.")
    else:
        for _, row in mid.sort_values("Datetime",ascending=False).iterrows():
            st.write(f"**{row['Fecha']} {row['Hora']} – {row['Symbol']}**")
            urls = [u.strip() for u in row["IdeaMissedURL"].split(",")]
            if not urls or urls==[""]:
                st.caption("Sin imagen")
            for url in urls:
                if url: 
                    st.markdown(f'<a href="{url}" target="_blank">'
                                f'<img src="{url}" width="880" '
                                'style="margin:3px;border:1px solid #ccc;"></a>',
                                unsafe_allow_html=True)
            st.write("---")

# ============================================================
# 8) EOD (Study Cases Canva)
# ============================================================
with st.expander("8) EOD (Study Cases Canva)", expanded=False):
    eod = df[df["EOD"].str.strip()!=""]
    if eod.empty:
        st.info("No hay EOD.")
    else:
        cards = [eod.iloc[i:i+2] for i in range(0,len(eod),2)]
        for pair in cards:
            cols = st.columns(2)
            for j,(_,tr) in enumerate(pair.iterrows()):
                with cols[j]:
                    st.write(f"**{tr['Fecha']} – {tr['Symbol']}**")
                    st.write(f"Categoría: {tr.get('ErrorCategory','–')}")
                    st.markdown(f"[Abrir EOD Canva]({tr['EOD']})")
                    st.write("---")

st.write("---\n*Fin del modo experimental.*")
