import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
import gspread

# ------------------------------------------------------
# 1) Configuración general de la página de Streamlit
# ------------------------------------------------------
st.set_page_config(
    page_title="Quantitative Journal",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ------------------------------------------------------
# 2) Conexión a Google Sheets
# ------------------------------------------------------
# SCOPES
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

creds_dict = st.secrets["quantitative_journal"]
credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
gc = gspread.authorize(credentials)

# Abre el spreadsheet por su ID (ajusta si cambias el ID o el método)
SPREADSHEET_KEY = "1D4AlYBD1EClp0gGe0qnxr8NeGMbpSvdOx8yHimQDmbE"
sh = gc.open_by_key(SPREADSHEET_KEY)

# Selecciona la pestaña "sheet1" 
worksheet = sh.worksheet("sheet1")

# ------------------------------------------------------
# (Opcional) Inicializar encabezados si la hoja está vacía o con encabezado diferente
# ------------------------------------------------------
existing_data = worksheet.get_all_values()

# Si no hay datos o la primera fila no incluye "Fecha" como columna,
# forzamos la creación de los encabezados correctos:
REQUIRED_HEADER = ["Fecha","Hora","Symbol","Type","Win/Loss/BE","USD","R","Screenshot","Comentarios"]
if not existing_data or len(existing_data[0]) < len(REQUIRED_HEADER) or existing_data[0] != REQUIRED_HEADER:
    worksheet.clear()
    worksheet.append_row(REQUIRED_HEADER)

# ------------------------------------------------------
# 3) Funciones auxiliares
# ------------------------------------------------------
def get_all_trades() -> pd.DataFrame:
    """
    Lee todos los registros de la hoja y los retorna como DataFrame
    asumiendo la primera fila como encabezados.
    """
    data = worksheet.get_all_records()  # Esto ignora la 1a fila (encabezado)
    df = pd.DataFrame(data)
    if not df.empty:
        # Convertir Fecha/Hora a datetime
        if "Fecha" in df.columns and "Hora" in df.columns:
            df["Datetime"] = pd.to_datetime(
                df["Fecha"] + " " + df["Hora"],
                errors="coerce"
            )
    return df

def append_trade(trade_dict: dict):
    """
    Agrega un nuevo trade al final de la Google Sheet.
    """
    row_values = [
        trade_dict.get("Fecha",""),
        trade_dict.get("Hora",""),
        trade_dict.get("Symbol",""),
        trade_dict.get("Type",""),
        trade_dict.get("Win/Loss/BE",""),
        trade_dict.get("USD",""),
        trade_dict.get("R",""),
        trade_dict.get("Screenshot",""),
        trade_dict.get("Comentarios","")
    ]
    worksheet.append_row(row_values)

def overwrite_sheet(df: pd.DataFrame):
    """
    Sube el DataFrame completo (con encabezados) a la hoja, 
    reemplazando todo.
    """
    worksheet.clear()
    # Encabezados
    worksheet.append_row(df.columns.tolist())
    # Filas
    rows = df.values.tolist()
    worksheet.append_rows(rows)

def calculate_r(usd_value: float, account_size=10000, risk_percent=0.3):
    """
    Calcula cuántas R's representa la ganancia/pérdida en 'usd_value'.
    risk_percent = 0.3% => 0.3
    account_size = 10000
    """
    risk_amount = account_size * (risk_percent / 100.0)  # 0.3% de 10k = 30
    R = float(usd_value) / risk_amount
    return round(R, 2)

def check_rules(df: pd.DataFrame, new_trade: dict) -> list:
    """
    Verifica las reglas:
    - Pausa de 10 mins tras un SL
    - Máximo 2 SL al día
    - 6 SL consecutivos en la semana
    Retorna lista de alertas si las hay.
    """
    alerts = []
    # 1) Pausa 10 min
    if new_trade["Win/Loss/BE"] == "Loss":
        if not df.empty:
            df_loss = df[df["Win/Loss/BE"] == "Loss"].copy()
            if not df_loss.empty:
                last_loss_time = pd.to_datetime(df_loss["Datetime"].iloc[-1])
                new_time = pd.to_datetime(new_trade["Fecha"] + " " + new_trade["Hora"])
                if (new_time - last_loss_time) < timedelta(minutes=10):
                    alerts.append("Violación: No esperaste 10 min después del último SL.")
    
    # 2) Máximo 2 SL en el día
    today_str = new_trade["Fecha"]
    if not df.empty:
        df_today = df[df["Fecha"] == today_str]
        losses_today = df_today[df_today["Win/Loss/BE"] == "Loss"].shape[0]
        # Ojo: si ya hay 2 Losses y se agrega un 3ro => violación
        if new_trade["Win/Loss/BE"] == "Loss" and losses_today >= 2:
            alerts.append("Violación: Llevas 2 SL hoy. No deberías operar más hoy.")
    
    # 3) 6 SL consecutivos en la semana
    if not df.empty:
        new_trade_datetime = pd.to_datetime(new_trade["Fecha"] + " " + new_trade["Hora"])
        week_number = new_trade_datetime.isocalendar().week
        year_number = new_trade_datetime.isocalendar().year

        df["week"] = df["Datetime"].apply(lambda x: x.isocalendar().week)
        df["year"] = df["Datetime"].apply(lambda x: x.isocalendar().year)
        df_this_week = df[(df["week"] == week_number) & (df["year"] == year_number)]
        df_this_week = df_this_week.sort_values("Datetime").reset_index(drop=True)

        consecutive_sl = 0
        max_consecutive_sl = 0
        for _, row in df_this_week.iterrows():
            if row["Win/Loss/BE"] == "Loss":
                consecutive_sl += 1
                max_consecutive_sl = max(max_consecutive_sl, consecutive_sl)
            else:
                consecutive_sl = 0
        
        # Al agregar este trade (si es Loss), incrementa
        if new_trade["Win/Loss/BE"] == "Loss":
            consecutive_sl += 1
            max_consecutive_sl = max(max_consecutive_sl, consecutive_sl)
        
        if max_consecutive_sl >= 6:
            alerts.append("Violación: 6 SL consecutivos esta semana. Debes parar hasta el próximo Lunes.")
    
    return alerts

# ------------------------------------------------------
# 4) Lectura del DF (inicial)
# ------------------------------------------------------
df = get_all_trades()

# ------------------------------------------------------
# Layout principal
# ------------------------------------------------------
st.title("Quantitative Journal - 10K Account")

# ======================================================
# SECCIÓN 1: Colección de datos (Trade Input)
# ======================================================
with st.expander("1. Colección de datos (Registrar un trade)", expanded=False):
    st.write("Completa los campos para agregar un nuevo trade.")
    
    col1, col2 = st.columns(2)
    with col1:
        date_str = st.date_input("Fecha").strftime("%Y-%m-%d")
        time_str = st.time_input("Hora").strftime("%H:%M:%S")
        symbol = st.selectbox("Símbolo", ["EURUSD", "GBPUSD", "Otro"])
        trade_type = st.selectbox("Tipo", ["Long", "Short"])
        result = st.selectbox("Resultado", ["Win", "Loss", "BE"])
    with col2:
        usd_pnl = st.number_input("USD ganados o perdidos (poner + o -)", value=0.0, step=0.01)
        screenshot_url = st.text_input("URL Screenshot TradingView (opcional)")
        comments = st.text_area("Comentarios (opcional)")
    
    # Si es "Loss" pero el valor es positivo => lo pasamos a negativo
    if result == "Loss" and usd_pnl > 0:
        usd_pnl = -abs(usd_pnl)
    
    # Cálculo de R
    r_value = calculate_r(usd_pnl, account_size=10000, risk_percent=0.3)
    
    if st.button("Agregar Trade"):
        new_trade = {
            "Fecha": date_str,
            "Hora": time_str,
            "Symbol": symbol,
            "Type": trade_type,
            "Win/Loss/BE": result,
            "USD": usd_pnl,
            "R": r_value,
            "Screenshot": screenshot_url,
            "Comentarios": comments
        }
        
        # Validar reglas
        alerts = check_rules(df, new_trade)
        if alerts:
            st.error(" / ".join(alerts))
            st.warning("Considera no registrar este trade si viola tus reglas.")
            # Decides si bloqueas el registro o solo adviertes.
        
        # Insertar
        append_trade(new_trade)
        st.success("Trade agregado exitosamente.")
        st.experimental_rerun()

# ------------------------------------------------------
# Releer DF tras insertar
# ------------------------------------------------------
df = get_all_trades()

# ======================================================
# SECCIÓN 2: Análisis/Feature Engineering
# ======================================================
with st.expander("2. Feature Engineering y Métricas", expanded=False):
    st.write("Métricas generales de la cuenta y visualizaciones principales.")
    
    if df.empty:
        st.warning("Aún no hay datos registrados.")
    else:
        # 2a) Resumen Win / Loss / BE
        total_trades = len(df)
        wins = len(df[df["Win/Loss/BE"] == "Win"])
        losses = len(df[df["Win/Loss/BE"] == "Loss"])
        be = len(df[df["Win/Loss/BE"] == "BE"])
        
        win_rate = round((wins/total_trades)*100, 2) if total_trades>0 else 0
        
        # 2b) Profit / Loss
        df["USD"] = pd.to_numeric(df["USD"], errors="coerce")
        gross_profit = df[df["USD"]>0]["USD"].sum()
        gross_loss = df[df["USD"]<0]["USD"].sum()
        net_profit = df["USD"].sum()
        
        # 2c) Profit Factor
        profit_factor = 0
        if gross_loss != 0:
            profit_factor = round(abs(gross_profit/gross_loss), 2)
        
        # 2d) Best / Worst
        best_profit = df["USD"].max()
        worst_loss = df["USD"].min()
        avg_profit = df[df["USD"]>0]["USD"].mean() if wins>0 else 0
        avg_loss = df[df["USD"]<0]["USD"].mean() if losses>0 else 0
        
        # 2e) Expectancy
        expectancy = round(df["USD"].mean(), 2) if total_trades>0 else 0
        
        # Mostrar métricas
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Trades", total_trades)
        col2.metric("Win Rate", f"{win_rate} %")
        col3.metric("Profit Factor", profit_factor)
        col4.metric("Expectancy", f"{expectancy} USD/trade")
        
        col5, col6, col7, col8 = st.columns(4)
        col5.metric("Gross Profit", round(gross_profit,2))
        col6.metric("Gross Loss", round(gross_loss,2))
        col7.metric("Net Profit", round(net_profit,2))
        col8.write(" ")  # placeholder
        
        # Pie chart Win/Loss/BE
        fig_pie = px.pie(
            names=["Win","Loss","BE"],
            values=[wins, losses, be],
            title="Distribución Win / Loss / BE"
        )
        st.plotly_chart(fig_pie, use_container_width=True)
        
        # 2f) Objetivos en R
        monthly_target_usd = 10000 * 0.14  # 14% de 10k => 1400$
        risk_amount = 10000 * 0.003       # 0.3% => 30
        total_R_acum = net_profit / risk_amount
        R_faltantes = (monthly_target_usd - net_profit)/risk_amount
        if R_faltantes < 0:
            trades_13_faltan = 0
        else:
            trades_13_faltan = int(np.ceil(R_faltantes/3))
        
        st.write(f"**R's acumuladas**: {round(total_R_acum,2)}")
        st.write(f"**R's faltantes** para objetivo de +14%: {round(R_faltantes,2)}")
        st.write(f"Trades 1:3 necesarios (aprox): {trades_13_faltan}")
        
        # 2g) Evolución de la cuenta
        df = df.sort_values("Datetime")
        df["Cumulative_USD"] = 10000 + df["USD"].cumsum()
        fig_line = px.line(
            df, 
            x="Datetime", 
            y="Cumulative_USD", 
            title="Evolución de la cuenta (USD)"
        )
        st.plotly_chart(fig_line, use_container_width=True)
        
        # 2h) % Actual vs -10% y +14%
        current_equity = df["Cumulative_USD"].iloc[-1]
        pct_change = ((current_equity - 10000)/10000)*100
        st.write(f"**Equity actual**: {round(current_equity,2)} USD | " 
                 f"**Variación**: {round(pct_change,2)}%")

# ======================================================
# SECCIÓN 3: Historial de Trades
# ======================================================
with st.expander("3. Historial de trades", expanded=False):
    if df.empty:
        st.warning("No hay trades registrados.")
    else:
        st.dataframe(df, use_container_width=True)

# ======================================================
# SECCIÓN 4: Editar / Borrar Trades
# ======================================================
with st.expander("4. Editar / Borrar trades", expanded=False):
    if df.empty:
        st.warning("No hay trades para editar/borrar.")
    else:
        st.write("Selecciona el índice del trade (fila) que quieres editar o borrar.")
        selected_idx = st.number_input(
            "Índice del trade (0-based)",
            min_value=0, 
            max_value=df.shape[0]-1, 
            step=1
        )
        
        selected_row = df.loc[selected_idx].to_dict()
        st.write("Trade seleccionado:")
        st.json(selected_row)
        
        # Botón BORRAR
        if st.button("Borrar este trade"):
            df = df.drop(selected_idx).reset_index(drop=True)
            overwrite_sheet(df)
            st.success("Trade borrado con éxito.")
            st.experimental_rerun()
        
        # Formulario EDITAR
        with st.form("edit_form"):
            st.write("Editar este trade:")
            new_fecha = st.text_input("Fecha", value=selected_row["Fecha"])
            new_hora = st.text_input("Hora", value=selected_row["Hora"])
            new_symbol = st.text_input("Symbol", value=selected_row["Symbol"])
            new_type = st.text_input("Type", value=selected_row["Type"])
            new_result = st.text_input("Win/Loss/BE", value=selected_row["Win/Loss/BE"])
            new_usd = st.number_input("USD", value=float(selected_row["USD"]), step=0.01)
            new_r = st.number_input("R", value=float(selected_row["R"]), step=0.01)
            new_screenshot = st.text_input("Screenshot", value=str(selected_row["Screenshot"]))
            new_comments = st.text_area("Comentarios", value=str(selected_row["Comentarios"]))
            
            submitted = st.form_submit_button("Guardar Cambios")
            if submitted:
                df.loc[selected_idx, "Fecha"] = new_fecha
                df.loc[selected_idx, "Hora"] = new_hora
                df.loc[selected_idx, "Symbol"] = new_symbol
                df.loc[selected_idx, "Type"] = new_type
                df.loc[selected_idx, "Win/Loss/BE"] = new_result
                df.loc[selected_idx, "USD"] = new_usd
                df.loc[selected_idx, "R"] = new_r
                df.loc[selected_idx, "Screenshot"] = new_screenshot
                df.loc[selected_idx, "Comentarios"] = new_comments
                
                overwrite_sheet(df)
                st.success("Trade editado con éxito.")
                st.experimental_rerun()

# Fin de la app
