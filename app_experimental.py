# -------------------  app_experimental.py  -------------------
import streamlit as st
import pandas as pd, numpy as np
import plotly.express as px, plotly.graph_objects as go
from google.oauth2.service_account import Credentials
import gspread

# -------------------------------------------------------------
# CONFIGURACIÓN
# -------------------------------------------------------------
st.set_page_config(page_title="Quantitative Journal – Experimental",
                   layout="wide", initial_sidebar_state="expanded")

scope      = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
creds      = Credentials.from_service_account_info(
                st.secrets["quantitative_journal"], scopes=scope)
gc         = gspread.authorize(creds)
ws         = gc.open_by_key("1D4AlYBD1EClp0gGe0qnxr8NeGMbpSvdOx8yHimQDmbE"
                ).worksheet("sheet1")

def get_all():
    df = pd.DataFrame(ws.get_all_records())
    if not df.empty and "Fecha" in df and "Hora" in df:
        df["Datetime"] = pd.to_datetime(df["Fecha"]+" "+df["Hora"], errors="coerce")
    return df

def calculate_drawdown(equity):
    peak = equity.cummax()
    return peak - equity

def sharpe_ratio(rets, rf=0):
    std = rets.std(ddof=1)
    return round((rets.mean()-rf)/std,2) if std!=0 else 0

def sortino_ratio(rets, rf=0):
    downside = rets[rets<0].std(ddof=1)
    return round((rets.mean()-rf)/downside,2) if downside!=0 else 0

def week_tag(dt):  return f"{dt.isocalendar().year}-W{dt.isocalendar().week}"
def month_tag(dt): return dt.strftime("%Y-%m")

# -------------------------------------------------------------
df = get_all()
st.title("Quantitative Journal – Experimental Features")

if df.empty:
    st.warning("No hay datos.")
    st.stop()

# -----------------------------------------------------------------
# Limpieza numérica
for col in ["Volume","Gross_USD","Commission","USD","R"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

df = df.sort_values("Datetime").reset_index(drop=True)
initial_cap = 60000
df["CumulUSD"] = initial_cap + df["USD"].cumsum()

# ===============================================================
# 1) Métricas avanzadas (consecutivos, DD, Sharpe, Sortino)
# ===============================================================
with st.expander("1) Métricas de rendimiento avanzado", expanded=False):
    consec_w = consec_l = max_w = max_l = 0
    for res in df["Win/Loss/BE"]:
        if res=="Win":
            consec_w +=1;  max_w=max(max_w,consec_w); consec_l=0
        elif res=="Loss":
            consec_l +=1;  max_l=max(max_l,consec_l); consec_w=0
        else:
            consec_w=consec_l=0
    c1,c2 = st.columns(2)
    c1.metric("Max Wins consecutivos", max_w)
    c2.metric("Max Loss consecutivos", max_l)

    dd = calculate_drawdown(df["CumulUSD"])
    st.write(f"**Máx Drawdown:** {round(dd.max(),2)} USD / "
             f"{round(100*dd.max()/initial_cap,2)} %")
    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(x=df["Datetime"], y=dd, mode="lines",
                                name="Drawdown", line=dict(color="red")))
    fig_dd.update_layout(title="Drawdown over time")
    st.plotly_chart(fig_dd, use_container_width=True)

    daily = df.groupby(df["Datetime"].dt.date)["USD"].sum()/initial_cap
    st.write(f"**Sharpe (aprox):** {sharpe_ratio(daily)}")
    st.write(f"**Sortino (aprox):** {sortino_ratio(daily)}")

# ===============================================================
# 2) Resúmenes semanales / mensuales
# ===============================================================
with st.expander("2) Resúmenes semanales / mensuales", expanded=False):
    df["WeekTag"]  = df["Datetime"].apply(week_tag)
    weekly = df.groupby("WeekTag").agg(Trades=("USD","count"),
                                       NetPNL=("USD","sum"),
                                       Volume=("Volume","sum")).reset_index()
    st.write("### Resumen semanal"); st.dataframe(weekly)
    st.plotly_chart(px.bar(weekly,x="WeekTag",y="NetPNL",title="PNL semanal"),
                    use_container_width=True)

    df["MonthTag"] = df["Datetime"].apply(month_tag)
    monthly = df.groupby("MonthTag").agg(Trades=("USD","count"),
                                         NetPNL=("USD","sum"),
                                         Volume=("Volume","sum")).reset_index()
    st.write("### Resumen mensual"); st.dataframe(monthly)
    st.plotly_chart(px.bar(monthly,x="MonthTag",y="NetPNL",title="PNL mensual"),
                    use_container_width=True)

# ===============================================================
# 3) Calendario / Timeline de trades
# ===============================================================
with st.expander("3) Calendario / Timeline de trades", expanded=False):
    # Agrupamos por día
    daily = df.groupby(df["Datetime"].dt.date).agg(
        Trades=("USD", "count"),
        NetPNL=("USD", "sum")
    ).reset_index().rename(columns={"Datetime": "DateOnly"})   # <<< FIX aquí

    st.write("#### Nº de trades por día")
    st.plotly_chart(
        px.bar(daily, x="DateOnly", y="Trades", title="# Trades por día",
               labels={"DateOnly": "Día", "Trades": "Cantidad"}),
        use_container_width=True
    )

    st.write("#### PnL diario")
    st.plotly_chart(
        px.bar(daily, x="DateOnly", y="NetPNL", title="PNL diario",
               labels={"DateOnly": "Día", "NetPNL": "PNL"}),
        use_container_width=True
    )


# ===============================================================
# 4) Análisis por symbol / hora
# ===============================================================
with st.expander("4) Análisis por Symbol / Hora", expanded=False):
    if "Symbol" in df:
        st.plotly_chart(px.bar(df.groupby("Symbol")["USD"].sum().reset_index(),
                               x="Symbol",y="USD",title="PNL por símbolo",
                               color="Symbol"), use_container_width=True)
    if "Hora" in df:
        df["HourInt"] = pd.to_datetime(df["Hora"],format="%H:%M:%S",
                                       errors="coerce").dt.hour
        st.plotly_chart(px.bar(df.groupby("HourInt")["USD"].sum().reset_index(),
                               x="HourInt",y="USD",title="PNL por hora"),
                        use_container_width=True)

# ===============================================================
# 5) Post‑Analysis / Etiquetas (Errores)
# ===============================================================
with st.expander("5) Post‑Analysis · Categorías de error", expanded=False):
    if "ErrorCategory" in df:
        loss_by_cat = df[df["USD"]<0].groupby("ErrorCategory")["USD"
                         ].sum().reset_index().rename(columns={"USD":"LossSum"})
        if loss_by_cat.empty:
            st.info("No hay pérdidas categorizadas.")
        else:
            st.dataframe(loss_by_cat)
            st.plotly_chart(px.bar(loss_by_cat,x="ErrorCategory",y="LossSum",
                                   title="Pérdidas por categoría",
                                   color="ErrorCategory"), use_container_width=True)
    else:
        st.info("Agrega la columna ErrorCategory en tu hoja.")

# ===============================================================
# 6) Loss Trade Reviews – galería agrupada
# ===============================================================
with st.expander("6) Loss Trade Reviews (galería)", expanded=False):
    if "LossTradeReviewURL" not in df.columns:
        st.warning("No existe la columna LossTradeReviewURL.")
    else:
        ltr_df = df[(df["LossTradeReviewURL"].str.strip() != "") &
                    (df["Win/Loss/BE"] == "Loss")].copy()
        if ltr_df.empty:
            st.info("No hay Loss Trade Reviews.")
        else:
            # opcional: filtrar por categoría
            cats = [c for c in ltr_df["ErrorCategory"].unique() if c]
            selected = st.multiselect("Filtrar por ErrorCategory", cats, default=cats)
            if selected:
                ltr_df = ltr_df[ltr_df["ErrorCategory"].isin(selected)]

            # recorrer trades
            for _, row in ltr_df.sort_values("Datetime", ascending=False).iterrows():
                st.write(f"**{row['Fecha']} {row['Hora']} – {row['Symbol']}**")
                st.write(f"Categoría: {row.get('ErrorCategory','–')}  |  "
                         f"Resolved: {row.get('Resolved','No')}")
                urls = [u.strip() for u in row["LossTradeReviewURL"].split(",")]
                img_cols = st.columns(min(3, len(urls)))  # 3 miniaturas por fila
                col_idx = 0
                for url in urls:
                    if url:
                        with img_cols[col_idx]:
                            st.image(url, width=880)
                        col_idx = (col_idx + 1) % len(img_cols)
                st.write("---")


# ===============================================================
# 7) EOD (End‑of‑Day) – presentaciones Canva
# ===============================================================
with st.expander("7) EOD (Study Cases Canva)", expanded=False):
    if "EOD" not in df.columns:
        st.warning("No existe la columna EOD.")
    else:
        eod_df = df[df["EOD"].str.strip() != ""].copy()
        if eod_df.empty:
            st.info("No hay EOD registrados.")
        else:
            # Tarjetas 2 por fila, orden cronológico inverso
            cards = [eod_df.iloc[i:i+2] for i in range(0, len(eod_df), 2)]
            for chunk in cards:
                cols = st.columns(2)
                for idx, (_, tr) in enumerate(chunk.iterrows()):
                    with cols[idx]:
                        st.write(f"**{tr['Fecha']} {tr['Hora']} – {tr['Symbol']}**")
                        st.write(f"Categoría: {tr.get('ErrorCategory','–')}")
                        st.markdown(f"[Abrir EOD Canva]({tr['EOD']})")
                        st.write("---")


st.write("---\n*Fin del modo experimental.*")
