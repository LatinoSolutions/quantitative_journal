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

# ===============================================================
# 1) Métricas de rendimiento avanzado
# ===============================================================
with st.expander("1) Métricas de rendimiento avanzado", expanded=False):

    # -- Consecutive wins / losses ----------
    cw = cl = mxw = mxl = 0
    for res in df_real["Win/Loss/BE"]:
        if res == "Win":
            cw += 1; mxw = max(mxw, cw); cl = 0
        elif res == "Loss":
            cl += 1; mxl = max(mxl, cl); cw = 0
        else:
            cw = cl = 0
    c1, c2 = st.columns(2)
    c1.metric("Max Wins consecutivos", mxw)
    c2.metric("Max Losses consecutivos", mxl)

    # -- Drawdown ----------
    dd = (df_real["CumulUSD"].cummax() - df_real["CumulUSD"])
    max_dd = dd.max()
    st.write(f"**Máx Drawdown:** {round(max_dd,2)} USD "
             f"({round(100*max_dd/initial_cap,2)} %)")
    st.plotly_chart(
        go.Figure(go.Scatter(x=df_real["Datetime"], y=dd,
                             mode="lines", line=dict(color="red")))
        .update_layout(title="Drawdown over time"),
        use_container_width=True
    )

    # -- Sharpe / Sortino (aprox diarios) ----------
    daily_ret = df_real.groupby(df_real["Datetime"].dt.date)["USD"].sum() / initial_cap
    sharpe  = daily_ret.mean() / daily_ret.std(ddof=1) if daily_ret.std(ddof=1) else 0
    downside = daily_ret[daily_ret<0].std(ddof=1)
    sortino = daily_ret.mean() / downside if downside else 0
    st.write(f"**Sharpe (aprox):** {round(sharpe,2)}  |  "
             f"**Sortino (aprox):** {round(sortino,2)}")

    # -- Break-Even Outcome ----------
    be_saved  = ((df_real["Win/Loss/BE"]=="BE") & (df_real["BEOutcome"]=="SavedCapital")).sum()
    be_missed = ((df_real["Win/Loss/BE"]=="BE") & (df_real["BEOutcome"]=="MissedOpportunity")).sum()
    st.write("#### Break-Even Outcomes")
    st.plotly_chart(
        px.bar(pd.DataFrame({"Outcome":["Saved","Missed"],
                             "Count":[be_saved,be_missed]}),
               x="Outcome",y="Count",text="Count",title="BE Outcome"),
        use_container_width=True)

    # -- Loss convertibles ----------
    conv_yes = ((df_real["Win/Loss/BE"]=="Loss") & (df_real["SecondTradeValid?"]=="Yes")).sum()
    conv_no  = ((df_real["Win/Loss/BE"]=="Loss") & (df_real["SecondTradeValid?"]=="No")).sum()
    conv_pct = 100*conv_yes/(conv_yes+conv_no) if (conv_yes+conv_no) else 0
    st.write(f"### Loss convertibles: {conv_yes}/{conv_yes+conv_no}  "
             f"→ **{conv_pct:.1f}%**")

    st.plotly_chart(
        px.bar(pd.DataFrame({"Status":["Convertible","No"],
                             "Count":[conv_yes,conv_no]}),
               x="Status",y="Count",text="Count",
               title="Loss convertibles (Yes vs No)"),
        use_container_width=True)

    with st.expander("Ver índices de Loss convertibles"):
        conv_list = df_real[(df_real["Win/Loss/BE"]=="Loss") &
                            (df_real["SecondTradeValid?"]=="Yes")][["Idx","Fecha","Symbol"]]
        st.dataframe(conv_list)



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
    # ---------- Lotes operados ----------
with st.expander("🚚 Lotes operados", expanded=False):
    df["WeekTag"]  = df["Datetime"].dt.strftime("%Y-W%U")
    df["MonthTag"] = df["Datetime"].dt.strftime("%Y-%m")
    weekly  = df.groupby("WeekTag")["Volume"].sum().reset_index()
    monthly = df.groupby("MonthTag")["Volume"].sum().reset_index()
    st.write("### Semana")
    st.bar_chart(weekly, x="WeekTag", y="Volume")
    st.write("### Mes")
    st.bar_chart(monthly, x="MonthTag", y="Volume")

# ---------- Loss / BE sin Review ----------
with st.expander("⚠️ Loss / BE sin Review", expanded=False):
    pend = df[(df["Win/Loss/BE"].isin(["Loss","BE"])) &
              (df["LossTradeReviewURL"]=="")]
    st.write(f"Pendientes: **{len(pend)}**")
    st.dataframe(pend[["Fecha","Hora","Symbol","USD","ErrorCategory"]])


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

# ===============================================================
# 6) Loss Trade Reviews – galería agrupada
# ===============================================================
with st.expander("Loss Trade Reviews (galería)", expanded=False):
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
                        st.markdown(
                            f'<a href="{url}" target="_blank">'
                            f'<img src="{url}" width="880" style="margin:4px; border:1px solid #DDD;">'
                            '</a>',
                            unsafe_allow_html=True
                        )


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
