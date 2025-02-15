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
# Cargamos credenciales desde secrets
creds_dict = st.secrets["quantitative_journal"]
credentials = Credentials.from_service_account_info(creds_dict)
gc = gspread.authorize(credentials)

# Nombre del Spreadsheet y Worksheet
SPREADSHEET_NAME = "quantitative_journal"     # <-- Ojo, este es el "document title" en Google
WORKSHEET_NAME = "10k account"                # <-- Nombre de la hoja dentro del spreadsheet

# Abrimos la hoja
sh = gc.open(WORKSHEET_NAME)  # si tu spreadsheet se llama "10k account", ponlo aquí
worksheet = sh.sheet1         # o sh.worksheet("nombre_de_la_hoja_si_tienes_varias")

# ------------------------------------------------------
# 3) Funciones auxiliares
# ------------------------------------------------------

def get_all_trades() -> pd.DataFrame:
    """
    Lee todos los registros de la hoja y los retorna como DataFrame.
    Asume la primera fila como encabezados.
    """
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)
    if not df.empty:
        # Opcional: convertir Fecha/Hora a datetime
        if "Fecha" in df.columns and "Hora" in df.columns:
            df["Datetime"] = pd.to_datetime(df["Fecha"] + " " + df["Hora"], errors="coerce")
        else:
            # Si tienes un solo campo de fecha/hora, ajusta según corresponda
            pass
    return df

def append_trade(trade_dict: dict):
    """
    Agrega un nuevo trade al final de la Google Sheet.
    Asume que las columnas en la hoja tienen el mismo orden que en 'trade_dict'.
    """
    # Asegúrate de que los campos estén en el orden correcto
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
    Sube el DataFrame completo a la hoja, 
    reemplazando todo (cuidado con esta operación).
    """
    worksheet.clear()
    # Escribimos la fila de encabezados
    worksheet.append_row(df.columns.tolist())
    # Escribimos cada fila
    rows = df.values.tolist()
    worksheet.append_rows(rows)

def calculate_r(usd_value: float, account_size=10000, risk_percent=0.3):
    """
    Calcula cuántas R's representa la ganancia/perdida en 'usd_value'.
    - risk_percent = 0.3% => 0.3
    - account_size = 10000
    """
    # El 'risk_amount' es 0.3% de 10k => 30 USD
    risk_amount = account_size * (risk_percent/100.0)
    # R = PnL / risk_amount
    R = float(usd_value) / risk_amount
    return round(R, 2)


def check_rules(df: pd.DataFrame, new_trade: dict) -> list:
    """
    Verifica las reglas de:
    - Pausa de 10 mins tras un Stop
    - Máximo 2 SL al día
    - 6 SL consecutivos en la semana
    Retorna lista de alertas.
    """
    alerts = []
    # 1) Pausa de 10 minutos si el trade anterior fue SL
    if new_trade["Win/Loss/BE"] == "Loss":
        # Buscar el último SL
        # df ya contiene trades anteriores. 
        # Ver si el último trade fue un Loss, y si la diferencia de tiempo es < 10 min
        if not df.empty:
            # Filtramos trades Loss
            df_loss = df[df["Win/Loss/BE"] == "Loss"].copy()
            if not df_loss.empty:
                last_loss_time = pd.to_datetime(df_loss["Datetime"].iloc[-1])
                new_time = pd.to_datetime(new_trade["Fecha"] + " " + new_trade["Hora"])
                if (new_time - last_loss_time) < timedelta(minutes=10):
                    alerts.append("Violación: No esperaste 10 min después del último SL.")
    
    # 2) Máximo 2 SL al día
    #   Ver cuántos SL van en el día de la fecha actual
    today_str = new_trade["Fecha"]  # asumiendo formato YYYY-mm-dd o similar
    if df.shape[0] > 0:
        df_today = df[df["Fecha"] == today_str]
        losses_today = df_today[df_today["Win/Loss/BE"] == "Loss"].shape[0]
        if new_trade["Win/Loss/BE"] == "Loss" and losses_today >= 2:
            alerts.append("Violación: Llevas 2 SL hoy. No deberías operar más hoy.")
    
    # 3) 6 SL consecutivos en la semana
    #   Asumiendo que la 'semana' se reinicia cada Lunes. 
    #   Aquí simplificaré la lógica, asumiendo ISO week de Pandas o algo similar.
    #   O podrías simplemente contar SL desde el Lunes de la semana actual.
    if not df.empty:
        # Tomamos la semana ISO de la fecha del new_trade
        new_trade_datetime = pd.to_datetime(new_trade["Fecha"] + " " + new_trade["Hora"])
        week_number = new_trade_datetime.isocalendar().week
        year_number = new_trade_datetime.isocalendar().year
        # Filtramos los trades de la misma semana
        df["week"] = df["Datetime"].apply(lambda x: x.isocalendar().week)
        df["year"] = df["Datetime"].apply(lambda x: x.isocalendar().year)
        df_this_week = df[(df["week"] == week_number) & (df["year"] == year_number)]
        # Contamos las pérdidas consecutivas
        # Para ello, ordenamos por fecha y revisamos la racha
        df_this_week = df_this_week.sort_values("Datetime").reset_index(drop=True)
        consecutive_sl = 0
        max_consecutive_sl = 0
        for i, row in df_this_week.iterrows():
            if row["Win/Loss/BE"] == "Loss":
                consecutive_sl += 1
                max_consecutive_sl = max(max_consecutive_sl, consecutive_sl)
            else:
                consecutive_sl = 0
        # Si añadimos un nuevo trade con SL, podemos incrementar
        if new_trade["Win/Loss/BE"] == "Loss":
            consecutive_sl += 1
            max_consecutive_sl = max(max_consecutive_sl, consecutive_sl)
        if max_consecutive_sl >= 6:
            alerts.append("Violación: 6 SL consecutivos en esta semana. Debes parar hasta el próximo Lunes.")

    return alerts

# ------------------------------------------------------
# 4) Lectura inicial del DF y layout Streamlit
# ------------------------------------------------------
df = get_all_trades()

st.title("Quantitative Journal - 10K Account")

# ======================================================
# SECCIÓN 1: Colección de datos (Trade Input)
# ======================================================
with st.expander("1. Colección de datos (Registrar un trade)", expanded=False):
    st.write("Completa los siguientes campos para agregar un nuevo trade a tu registro.")
    
    col1, col2 = st.columns(2)
    with col1:
        date_str = st.date_input("Fecha").strftime("%Y-%m-%d")
        time_str = st.time_input("Hora").strftime("%H:%M:%S")
        symbol = st.selectbox("Símbolo", ["EURUSD", "GBPUSD", "Otro"])
        trade_type = st.selectbox("Tipo", ["Long", "Short"])
        result = st.selectbox("Resultado", ["Win", "Loss", "BE"])  # break-even?
    with col2:
        usd_pnl = st.number_input("USD ganados o perdidos (poner + o -)", value=0.0, step=0.01)
        screenshot_url = st.text_input("URL Screenshot TradingView (opcional)")
        comments = st.text_area("Comentarios (opcional)")
    
    # Convertir a negativo si la selección es "Loss" y el valor es positivo
    if result == "Loss" and usd_pnl > 0:
        usd_pnl = -abs(usd_pnl)
    
    # Cálculo de R
    r_value = calculate_r(usd_pnl, account_size=10000, risk_percent=0.3)
    
    if st.button("Agregar Trade"):
        # Creamos el diccionario a subir
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
        
        # Verificamos reglas
        alerts = check_rules(df, new_trade)
        if alerts:
            st.error(" / ".join(alerts))
            st.warning("Considera NO registrar este trade si viola tus reglas de gestión.")
            # Aún así, podrías permitir guardar o no el trade.
            # Decisión personal. Aquí solo muestro la alerta.
        
        # Agregamos a la hoja
        append_trade(new_trade)
        st.success("Trade agregado exitosamente.")
        st.experimental_rerun()  # recarga la app para actualizar DF

# Releemos el DF tras potencial inserción
df = get_all_trades()

# ======================================================
# SECCIÓN 2: Análisis/Feature Engineering
# ======================================================
with st.expander("2. Feature Engineering y Métricas", expanded=False):
    st.write("Métricas generales de la cuenta y visualizaciones principales.")
    
    if df.empty:
        st.warning("Aún no hay datos registrados.")
    else:
        # 2a) Contar Win / Loss / BE
        total_trades = df.shape[0]
        wins = df[df["Win/Loss/BE"] == "Win"].shape[0]
        losses = df[df["Win/Loss/BE"] == "Loss"].shape[0]
        be = df[df["Win/Loss/BE"] == "BE"].shape[0]
        
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
        
        # 2e) Expectancy: prom (USD) por trade
        expectancy = round(df["USD"].mean(), 2) if total_trades>0 else 0
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Trades", total_trades)
        col2.metric("Win Rate", f"{win_rate} %")
        col3.metric("Profit Factor", profit_factor)
        col4.metric("Expectancy", f"{expectancy} USD/trade")
        
        col5, col6, col7, col8 = st.columns(4)
        col5.metric("Gross Profit", round(gross_profit,2))
        col6.metric("Gross Loss", round(gross_loss,2))
        col7.metric("Net Profit", round(net_profit,2))
        col8.write("")  # placeholder
        
        # Pie chart Win/Loss/BE
        fig_pie = px.pie(
            names=["Win","Loss","BE"],
            values=[wins, losses, be],
            title="Win / Loss / BE Distribution"
        )
        st.plotly_chart(fig_pie, use_container_width=True)
        
        # -----------------------------------------------------
        # 2f) Objetivos en R
        #   14% = 1400$ al mes => risk=30$ => 1R = 30$
        #   total_R = sum(USD) / 30
        #   # trades 1:3 => 3R por trade => # trades faltantes
        # -----------------------------------------------------
        monthly_target_usd = 10000 * 0.14  # 14% de 10k => 1400$
        risk_amount = 10000 * 0.003  # 0.3% => 30
        total_R_acum = net_profit / risk_amount
        R_faltantes = (monthly_target_usd - net_profit)/risk_amount  # cuántas R hacen falta
        # asumiendo trades 1:3 => 3R de ganancia
        if R_faltantes < 0:
            trades_13_faltan = 0
        else:
            trades_13_faltan = np.ceil(R_faltantes/3)
        
        st.write(f"**R's acumuladas**: {round(total_R_acum,2)}")
        st.write(f"**R's faltantes** para objetivo de 14%: {round(R_faltantes,2)}")
        st.write(f"Número aproximado de trades 1:3 que necesitas: {int(trades_13_faltan)}")
        
        # -----------------------------------------------------
        # 2g) Evolución de Capital en un line chart
        #     Partimos de 10k, y sumamos la columna USD cumm.
        # -----------------------------------------------------
        df = df.sort_values("Datetime")
        df["Cumulative_USD"] = 10000 + df["USD"].cumsum()
        fig_line = px.line(df, x="Datetime", y="Cumulative_USD", title="Evolución de la cuenta")
        st.plotly_chart(fig_line, use_container_width=True)
        
        # -----------------------------------------------------
        # 2h) % Actual vs drawdown de -10% y meta de +14%
        # -----------------------------------------------------
        current_equity = df["Cumulative_USD"].iloc[-1]
        pct_change = ((current_equity - 10000)/10000)*100
        st.write(f"**Equity actual**: {round(current_equity,2)} USD | **Variación**: {round(pct_change,2)}%")
        
        # Puedes crear un gauge chart con Plotly también, pero aquí lo simplifico
        # Ejemplo de bullet chart o algo similar se puede hacer con go.Figure()

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
        # Seleccionar un trade mediante índice
        st.write("Selecciona el índice del trade (fila) que quieres editar o borrar.")
        selected_idx = st.number_input("Índice del trade (0-based)", min_value=0, max_value=df.shape[0]-1, step=1)
        
        selected_row = df.loc[selected_idx].to_dict()
        st.write("Trade seleccionado:")
        st.json(selected_row)
        
        # Botón BORRAR
        if st.button("Borrar este trade"):
            df = df.drop(selected_idx).reset_index(drop=True)
            overwrite_sheet(df)
            st.success("Trade borrado con éxito.")
            st.experimental_rerun()
        
        # Formulario para EDITAR
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

# ======================================================
# FIN DE LA APP
# ======================================================
