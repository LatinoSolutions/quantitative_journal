import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
import gspread

###############################
# CONFIGURACIÓN DE LA APP
###############################
st.set_page_config(
    page_title="Quantitative Journal - Experimental",
    layout="wide",
    initial_sidebar_state="expanded"
)

###############################
# CONEXIÓN A GOOGLE SHEETS
###############################
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
creds_dict = st.secrets["quantitative_journal"]
credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
gc = gspread.authorize(credentials)

SPREADSHEET_KEY = "1D4AlYBD1EClp0gGe0qnxr8NeGMbpSvdOx8yHimQDmbE"  # Ajusta al tuyo
sh = gc.open_by_key(SPREADSHEET_KEY)
worksheet = sh.worksheet("sheet1")

###############################
# FUNCIONES AUXILIARES
###############################
def get_all_trades() -> pd.DataFrame:
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)
    if not df.empty and "Fecha" in df.columns and "Hora" in df.columns:
        df["Datetime"] = pd.to_datetime(df["Fecha"] + " " + df["Hora"], errors="coerce")
    return df

def calculate_drawdown(equity_series: pd.Series):
    """
    Retorna un pd.Series con la cantidad de drawdown en cada punto.
    drawdown = (peak_so_far - current_equity)
    """
    peak = equity_series.cummax()
    drawdown = peak - equity_series
    return drawdown

def calculate_sharpe(returns_series, rf=0.0):
    """
    Calcula Sharpe Ratio = (mean(returns) - rf) / std(returns).
    Supone returns_series diario o semanal. 
    rf = tasa libre de riesgo (0 por simplificar).
    """
    avg_ret = returns_series.mean()
    std_ret = returns_series.std(ddof=1)
    if std_ret == 0:
        return 0
    sharpe = (avg_ret - rf) / std_ret
    return round(sharpe, 2)

def calculate_sortino(returns_series, rf=0.0):
    """
    Sortino ratio = (mean(returns)-rf) / std(returns<0).
    """
    avg_ret = returns_series.mean()
    neg_ret = returns_series[returns_series < 0]
    std_neg = neg_ret.std(ddof=1)
    if std_neg == 0:
        return 0
    sortino = (avg_ret - rf) / std_neg
    return round(sortino, 2)

def get_week_number(date):
    # Devuelve un string "YYYY-WW" para agrupar
    return f"{date.isocalendar().year}-W{date.isocalendar().week}"

def get_month_number(date):
    # Devuelve un string "YYYY-MM"
    return date.strftime("%Y-%m")

###############################
# LÓGICA PRINCIPAL
###############################
st.title("Quantitative Journal - Experimental Features")

df = get_all_trades()
if df.empty:
    st.warning("No hay datos registrados en la hoja. Agrega trades y luego vuelve.")
    st.stop()

# Convertir a numérico
for col_name in ["Volume","Gross_USD","Commission","USD","R"]:
    if col_name in df.columns:
        df[col_name] = pd.to_numeric(df[col_name], errors="coerce")

# Ordenar por fecha
df = df.sort_values("Datetime").reset_index(drop=True)

# CAPITAL INICIAL (Ajusta si deseas)
initial_capital = 60000

# Calculamos la curva de equity
df["Cumulative_USD"] = initial_capital + df["USD"].cumsum()

###############################
# 1. Métricas de rendimiento avanzado
###############################
with st.expander("1) Métricas de rendimiento avanzado", expanded=False):
    st.write("### Consecutive Wins / Losses")
    consecutive_w = 0
    max_consecutive_w = 0
    consecutive_l = 0
    max_consecutive_l = 0

    for i, row in df.iterrows():
        result = row.get("Win/Loss/BE","")
        if result == "Win":
            consecutive_w += 1
            max_consecutive_w = max(max_consecutive_w, consecutive_w)
            consecutive_l = 0
        elif result == "Loss":
            consecutive_l += 1
            max_consecutive_l = max(max_consecutive_l, consecutive_l)
            consecutive_w = 0
        else:  # BE
            consecutive_w = 0
            consecutive_l = 0

    col1, col2 = st.columns(2)
    col1.metric("Max consecutive Wins", max_consecutive_w)
    col2.metric("Max consecutive Losses", max_consecutive_l)

    st.write("### Drawdown")
    dd_series = calculate_drawdown(df["Cumulative_USD"])
    max_dd = dd_series.max()  
    max_dd_pct = (max_dd / initial_capital) * 100 if initial_capital != 0 else 0
    st.write(f"**Máximo Drawdown**: {round(max_dd,2)} USD / {round(max_dd_pct,2)}%")

    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(
        x=df["Datetime"],
        y=dd_series,
        mode="lines",
        name="Drawdown (USD)",
        line=dict(color="red")
    ))
    fig_dd.update_layout(title="Drawdown Over Time", xaxis_title="Fecha", yaxis_title="Drawdown (USD)")
    st.plotly_chart(fig_dd, use_container_width=True)

    st.write("### Sharpe / Sortino (aprox)")
    df["DateOnly"] = df["Datetime"].dt.date
    daily_pnl = df.groupby("DateOnly")["USD"].sum().reset_index()
    daily_pnl["Return"] = daily_pnl["USD"] / initial_capital

    sharpe = calculate_sharpe(daily_pnl["Return"])
    sortino = calculate_sortino(daily_pnl["Return"])
    st.write(f"**Sharpe Ratio (aprox)**: {sharpe}")
    st.write(f"**Sortino Ratio (aprox)**: {sortino}")

###############################
# 2. Resúmenes semanales / mensuales
###############################
with st.expander("2) Resúmenes semanales / mensuales", expanded=False):
    df["WeekTag"] = df["Datetime"].apply(lambda x: get_week_number(x) if pd.notnull(x) else "")
    weekly_stats = df.groupby("WeekTag").agg(
        Trades=("USD","count"),
        NetPNL=("USD","sum"),
        VolumeSum=("Volume","sum") if "Volume" in df.columns else ("USD","count"),
    ).reset_index()

    st.write("### Resumen Semanal")
    st.dataframe(weekly_stats)

    fig_week = px.bar(
        weekly_stats,
        x="WeekTag",
        y="NetPNL",
        title="PNL semanal",
        labels={"WeekTag":"Semana","NetPNL":"PNL"}
    )
    st.plotly_chart(fig_week, use_container_width=True)

    df["MonthTag"] = df["Datetime"].apply(lambda x: get_month_number(x) if pd.notnull(x) else "")
    monthly_stats = df.groupby("MonthTag").agg(
        Trades=("USD","count"),
        NetPNL=("USD","sum"),
        VolumeSum=("Volume","sum") if "Volume" in df.columns else ("USD","count"),
    ).reset_index()

    st.write("### Resumen Mensual")
    st.dataframe(monthly_stats)

    fig_month = px.bar(
        monthly_stats,
        x="MonthTag",
        y="NetPNL",
        title="PNL mensual",
        labels={"MonthTag":"Mes","NetPNL":"PNL"}
    )
    st.plotly_chart(fig_month, use_container_width=True)

    st.write("""
    *Tip: podrías “congelar” datos al inicio de cada semana/mes, 
    para guardar un 'snapshot' y hacer un reporte especial.*
    """)

###############################
# 3. Calendario / Timeline de trades
###############################
with st.expander("3) Calendario / Timeline de trades", expanded=False):
    df["DateOnly"] = df["Datetime"].dt.date
    daily_counts = df.groupby("DateOnly").agg(
        Trades=("USD","count"),
        NetPNL=("USD","sum")
    ).reset_index()

    st.write("#### # de trades por día")
    fig_trades_per_day = px.bar(
        daily_counts, x="DateOnly", y="Trades",
        title="Trades por Día",
        labels={"DateOnly":"Día","Trades":"Cantidad de Trades"}
    )
    st.plotly_chart(fig_trades_per_day, use_container_width=True)

    st.write("#### PnL diario")
    fig_pnl_per_day = px.bar(
        daily_counts, x="DateOnly", y="NetPNL",
        title="PNL por Día",
        labels={"DateOnly":"Día","NetPNL":"PNL Diario"}
    )
    st.plotly_chart(fig_pnl_per_day, use_container_width=True)

    st.info("""
    Si deseas un calendario más vistoso (con celdas de calendario 
    y gradientes de color), podrías usar librerías como 'calplot' 
    en un entorno local, o algún componente de Streamlit, 
    pero no viene por defecto.
    """)

###############################
# 4. Análisis por Symbol / Hora
###############################
with st.expander("4) Análisis por Symbol / Hora", expanded=False):
    if "Symbol" in df.columns:
        symbol_stats = df.groupby("Symbol").agg(
            Trades=("USD","count"),
            NetPNL=("USD","sum")
        ).reset_index()
        st.write("#### PnL por Symbol")
        fig_symbol = px.bar(
            symbol_stats, x="Symbol", y="NetPNL",
            title="PNL por Símbolo",
            labels={"Symbol":"Símbolo","NetPNL":"PNL"},
            color="Symbol"
        )
        st.plotly_chart(fig_symbol, use_container_width=True)

    if "Hora" in df.columns:
        df["HourInt"] = pd.to_datetime(df["Hora"], format="%H:%M:%S", errors="coerce").dt.hour
        hour_stats = df.groupby("HourInt").agg(
            Trades=("USD","count"),
            NetPNL=("USD","sum")
        ).reset_index()
        st.write("#### PnL por Hora del día")
        fig_hour = px.bar(
            hour_stats, x="HourInt", y="NetPNL",
            title="PNL por Hora",
            labels={"HourInt":"Hora (0-23)","NetPNL":"PNL"}
        )
        st.plotly_chart(fig_hour, use_container_width=True)
    else:
        st.warning("No existe la columna 'Hora'. Imposible analizar por hora.")

###############################
# 5. Mejora de Post-Analysis (Etiquetas)
###############################
with st.expander("5) Post-Analysis y Etiquetas", expanded=False):
    st.write("""
    Si creaste una columna 'ErrorCategory' en la hoja,
    aquí podríamos agrupar las pérdidas por tipo de error. 
    Ejemplo: "Psicológico", "Noticia", "FOMO", "Técnico", etc.
    """)

    if "ErrorCategory" in df.columns:
        cat_loss_stats = df[df["USD"]<0].groupby("ErrorCategory").agg(
            LossTrades=("USD","count"),
            LossSum=("USD","sum")
        ).reset_index()

        if cat_loss_stats.empty:
            st.info("No hay pérdidas registradas o no hay categorías de error.")
        else:
            st.write("#### Pérdidas por categoría de error")
            st.dataframe(cat_loss_stats)

            fig_cat = px.bar(
                cat_loss_stats, x="ErrorCategory", y="LossSum",
                title="Suma de pérdidas por Categoría",
                labels={"ErrorCategory":"Categoría","LossSum":"USD Perdidos"},
                color="ErrorCategory"
            )
            st.plotly_chart(fig_cat, use_container_width=True)
    else:
        st.info("No existe la columna 'ErrorCategory' en la hoja. Crea la columna y etiquétalos.")

###############################
# 6. Study Cases con mini-imágenes
###############################
with st.expander("6) Study Cases con imágenes", expanded=False):
    st.write("""
    Asumiendo que tienes una columna 'StudyCaseImageURL' 
    con links directos a una imagen (PNG, JPG, etc.). 
    Mostramos miniaturas y un link.
    """)

    if "StudyCaseImageURL" not in df.columns:
        st.warning("No existe la columna 'StudyCaseImageURL'. Crea la columna y agrega enlaces a tus imágenes.")
    else:
        df_imgs = df[df["StudyCaseImageURL"].notnull() & (df["StudyCaseImageURL"]!="")].copy()
        if df_imgs.empty:
            st.info("No hay Study Cases con imagen todavía.")
        else:
            for i, row in df_imgs.iterrows():
                fecha = row.get("Fecha","")
                symbol = row.get("Symbol","")
                img_url = row.get("StudyCaseImageURL","")
                st.write(f"**Trade**: {i} | {fecha} | {symbol}")
                st.image(img_url, width=300)
                st.markdown(f"[Ver tamaño completo]({img_url})")
                st.write("---")

###############################
# 7. Panel de Study Cases (tarjetas)
###############################
with st.expander("7) Panel de Study Cases (tarjetas)", expanded=False):
    st.write("""
    Un panel estilo 'tarjetas' que filtra por `ErrorCategory` 
    y muestra `StudyCaseLink` y `StudyCaseImageURL`. 
    """)
    # Si no existen las columnas, mostramos aviso
    needed_cols = ["StudyCaseLink","ErrorCategory","StudyCaseImageURL"]
    missing_cols = [c for c in needed_cols if c not in df.columns]
    if missing_cols:
        st.warning(f"No existen las columnas: {missing_cols}. Crea/edita tu hoja para usarlas.")
    else:
        # Filtramos solo trades con StudyCaseLink != ""
        df_sc = df[df["StudyCaseLink"].notnull() & (df["StudyCaseLink"]!="")].copy()
        df_sc = df_sc.sort_values("Datetime", ascending=False).reset_index(drop=True)
        if df_sc.empty:
            st.info("No hay Study Cases registrados (StudyCaseLink vacío).")
        else:
            # MULTISELECT para filtrar ErrorCategory
            all_cats = [c for c in df_sc["ErrorCategory"].unique().tolist() if c]
            selected_cats = st.multiselect("Filtrar por Error Category", options=all_cats, default=all_cats)
            filtered_df = df_sc.copy()
            if selected_cats:
                filtered_df = filtered_df[ filtered_df["ErrorCategory"].isin(selected_cats) ]

            st.write(f"**Study Cases encontrados**: {len(filtered_df)}")

            # Tarjetas 2 por fila
            cards_per_row = 2
            rows = [filtered_df.iloc[i:i+cards_per_row] for i in range(0, len(filtered_df), cards_per_row)]

            for row_chunk in rows:
                cols = st.columns(cards_per_row)
                for i, (idx, trade) in enumerate(row_chunk.iterrows()):
                    with cols[i]:
                        fecha = trade.get("Fecha","")
                        hora = trade.get("Hora","")
                        symbol = trade.get("Symbol","")
                        errorcat = trade.get("ErrorCategory","N/A")
                        resolved = trade.get("Resolved","No")
                        canva_link = trade.get("StudyCaseLink","")
                        mini_img = trade.get("StudyCaseImageURL","")

                        st.write(f"**Fecha**: {fecha} {hora}")
                        st.write(f"**Símbolo**: {symbol}")
                        st.write(f"**Categoría**: {errorcat}")
                        st.write(f"**Resuelto?**: {resolved}")

                        # Mostramos la imagen en mini, si existe
                        if mini_img:
                            st.image(mini_img, width=250)

                        # Link a Canva o lo que uses
                        st.markdown(f"[Abrir StudyCase Link]({canva_link})")

                        st.write("---")

st.write("""
---
### Nota final
Esta app es un prototipo con ideas avanzadas. 
No edita tus trades (solo lectura). 
Si algo te sobra o te falta, ajusta la sección correspondiente. 
---
""")
