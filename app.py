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
    page_title="Bru's QuantJournal",
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

SPREADSHEET_KEY = "1D4AlYBD1EClp0gGe0qnxr8NeGMbpSvdOx8yHimQDmbE"
sh = gc.open_by_key(SPREADSHEET_KEY)
worksheet = sh.worksheet("sheet1")

# Nuevo encabezado que incluye Volume, Commission y Post-Analysis
REQUIRED_HEADER = [
    "Fecha","Hora","Symbol","Type","Volume","Win/Loss/BE",
    "Gross_USD","Commission","USD","R","Screenshot","Comentarios","Post-Analysis"
]

# Si la hoja está completamente vacía, escribimos el encabezado nuevo.
existing_data = worksheet.get_all_values()
if not existing_data:
    worksheet.append_row(REQUIRED_HEADER)
else:
    # Si la primera fila NO coincide con el nuevo encabezado exacto, lo forzamos.
    # (Cuidado: esto borra la hoja si difiere. Haz copia si no deseas perder datos.)
    if existing_data[0] != REQUIRED_HEADER:
        worksheet.clear()
        worksheet.append_row(REQUIRED_HEADER)


# ------------------------------------------------------
# 3) Funciones auxiliares
# ------------------------------------------------------
def get_all_trades() -> pd.DataFrame:
    """
    Lee todos los registros de la hoja y los retorna como DataFrame.
    """
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)
    # Convertir a datetime si existen esas columnas
    if not df.empty and "Fecha" in df.columns and "Hora" in df.columns:
        df["Datetime"] = pd.to_datetime(df["Fecha"] + " " + df["Hora"], errors="coerce")
    return df

def append_trade(trade_dict: dict):
    """
    Agrega un nuevo trade como una fila al final de la hoja.
    """
    row_values = [
        trade_dict.get("Fecha",""),
        trade_dict.get("Hora",""),
        trade_dict.get("Symbol",""),
        trade_dict.get("Type",""),
        trade_dict.get("Volume",""),
        trade_dict.get("Win/Loss/BE",""),
        trade_dict.get("Gross_USD",""),
        trade_dict.get("Commission",""),
        trade_dict.get("USD",""),
        trade_dict.get("R",""),
        trade_dict.get("Screenshot",""),
        trade_dict.get("Comentarios",""),
        trade_dict.get("Post-Analysis","")
    ]
    worksheet.append_row(row_values)

def overwrite_sheet(df: pd.DataFrame):
    """
    Reemplaza toda la hoja con el DataFrame + encabezados.
    1) Convierte 'Datetime' a string si existe (evita TypeError).
    2) Reemplaza NaN por "" para que no falle la serialización.
    3) Limpia la hoja, reescribe encabezados y luego todas las filas.
    """
    if "Datetime" in df.columns and pd.api.types.is_datetime64_any_dtype(df["Datetime"]):
        df["Datetime"] = df["Datetime"].dt.strftime("%Y-%m-%d %H:%M:%S")

    df = df.fillna("")  # Reemplazar NaN con ""
    worksheet.clear()
    worksheet.append_row(df.columns.tolist())
    rows = df.values.tolist()
    worksheet.append_rows(rows)

def update_single_row_in_sheet(row_index: int, trade_dict: dict):
    """
    Actualiza SOLO la fila en Google Sheets (row_index es 0-based en el DF).
    - En la hoja, la primera fila (row=1) son los encabezados,
      por lo que el trade #0 está en la fila 2, etc.
    - Ajustar el rango A:M (13 columnas) si cambia tu estructura.
    """
    sheet_row = row_index + 2  # (encabezados en la fila 1)
    row_values = [
        trade_dict.get("Fecha",""),
        trade_dict.get("Hora",""),
        trade_dict.get("Symbol",""),
        trade_dict.get("Type",""),
        trade_dict.get("Volume",""),
        trade_dict.get("Win/Loss/BE",""),
        trade_dict.get("Gross_USD",""),
        trade_dict.get("Commission",""),
        trade_dict.get("USD",""),
        trade_dict.get("R",""),
        trade_dict.get("Screenshot",""),
        trade_dict.get("Comentarios",""),
        trade_dict.get("Post-Analysis","")
    ]
    # Actualizamos la fila en la hoja
    worksheet.update(f"A{sheet_row}:M{sheet_row}", [row_values])

def calculate_r(usd_value: float, account_size=60000, risk_percent=0.25):
    """
    Calcula cuántas R's representa la ganancia/pérdida en 'usd_value'.
    Por defecto, tomamos 60k como tamaño de cuenta.
    OJO: risk_percent=0.25 equivale a 0.25%.
    """
    risk_amount = account_size * (risk_percent / 100.0)  # 0.25% => 0.0025 * 60000 = 150
    R = float(usd_value) / risk_amount
    return round(R, 2)

def check_rules(df: pd.DataFrame, new_trade: dict) -> list:
    """
    Valida las reglas (esperar 10 min tras un SL, no sobrepasar 2 SL diarios, no más de 6 SL consecutivos/semana, etc.).
    Retorna una lista de strings con las violaciones encontradas.
    """
    alerts = []
    if new_trade["Win/Loss/BE"] == "Loss":
        if not df.empty:
            df_loss = df[df["Win/Loss/BE"] == "Loss"].copy()
            if not df_loss.empty:
                last_loss_time = pd.to_datetime(df_loss["Datetime"].iloc[-1])
                new_time = pd.to_datetime(new_trade["Fecha"] + " " + new_trade["Hora"])
                if (new_time - last_loss_time) < timedelta(minutes=10):
                    alerts.append("Violación: No esperaste 10 min después del último SL.")

    today_str = new_trade["Fecha"]
    if not df.empty:
        df_today = df[df["Fecha"] == today_str]
        losses_today = df_today[df_today["Win/Loss/BE"] == "Loss"].shape[0]
        if new_trade["Win/Loss/BE"] == "Loss" and losses_today >= 2:
            alerts.append("Violación: Llevas 2 SL hoy. No deberías operar más hoy.")

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
        if new_trade["Win/Loss/BE"] == "Loss":
            consecutive_sl += 1
            max_consecutive_sl = max(max_consecutive_sl, consecutive_sl)

        if max_consecutive_sl >= 6:
            alerts.append("Violación: 6 SL consecutivos esta semana. Debes parar hasta el próximo Lunes.")

    return alerts


# ------------------------------------------------------
# 4) Lectura inicial del DF y Layout
# ------------------------------------------------------
df = get_all_trades()

st.title("Quantitative Journal - 60K Account")

# ======================================================
# SECCIÓN 1: Colección de datos (Registrar un trade)
# ======================================================
with st.expander("1. Colección de datos (Registrar un trade)", expanded=False):
    st.write("Completa los campos para agregar un nuevo trade.")

    col1, col2 = st.columns(2)
    with col1:
        date_str = st.date_input("Fecha").strftime("%Y-%m-%d")
        time_str = st.time_input("Hora").strftime("%H:%M:%S")
        symbol = st.selectbox("Símbolo", ["EURUSD", "GBPUSD", "Otro"])
        trade_type = st.selectbox("Tipo", ["Long", "Short"])
        volume = st.number_input("Volume (lotes)", min_value=0.0, step=0.01)
        result = st.selectbox("Resultado", ["Win", "Loss", "BE"])
    with col2:
        gross_usd = st.number_input("Gross USD (PnL bruto sin comisión)", value=0.0, step=0.01)
        screenshot_url = st.text_input("URL Screenshot (opcional)")
        comments = st.text_area("Comentarios (opcional)")
        post_analysis = st.text_area("Post-Analysis (opcional)")

    # Forzamos que si es "Loss" y el valor bruto es positivo, lo convirtamos a negativo
    if result == "Loss" and gross_usd > 0:
        gross_usd = -abs(gross_usd)

    # Comisión (4 USD por lote)
    commission = volume * 4.0
    # Neto
    net_usd = gross_usd - commission
    # R
    r_value = calculate_r(net_usd, account_size=60000, risk_percent=0.25)

    if st.button("Agregar Trade"):
        new_trade = {
            "Fecha": date_str,
            "Hora": time_str,
            "Symbol": symbol,
            "Type": trade_type,
            "Volume": volume,
            "Win/Loss/BE": result,
            "Gross_USD": gross_usd,
            "Commission": commission,
            "USD": net_usd,
            "R": r_value,
            "Screenshot": screenshot_url,
            "Comentarios": comments,
            "Post-Analysis": post_analysis
        }

        # Chequear reglas
        alerts = check_rules(df, new_trade)
        if alerts:
            st.error(" / ".join(alerts))
            st.warning("Considera no registrar este trade si viola tus reglas.")

        # Agregar a la hoja
        append_trade(new_trade)
        st.success("Trade agregado exitosamente.")

        # Actualizamos df en memoria para mostrarlo de inmediato
        df = get_all_trades()

# ======================================================
# SECCIÓN 2: Feature Engineering y Métricas
# ======================================================
with st.expander("2. Feature Engineering y Métricas", expanded=False):
    st.write("Métricas generales de la cuenta y visualizaciones principales.")

    if df.empty:
        st.warning("Aún no hay datos registrados.")
    else:
        # Convertir a tipo numérico las columnas numéricas
        for col_name in ["Volume","Gross_USD","Commission","USD","R"]:
            if col_name in df.columns:
                df[col_name] = pd.to_numeric(df[col_name], errors="coerce")

        total_trades = len(df)
        wins = len(df[df["Win/Loss/BE"] == "Win"])
        losses = len(df[df["Win/Loss/BE"] == "Loss"])
        be = len(df[df["Win/Loss/BE"] == "BE"])
        win_rate = round((wins / total_trades) * 100, 2) if total_trades > 0 else 0

        # Ganancia/pérdida neta total => sum de la columna "USD" (que ya es neta)
        gross_profit = df[df["USD"] > 0]["USD"].sum()
        gross_loss = df[df["USD"] < 0]["USD"].sum()
        net_profit = df["USD"].sum()

        # Profit Factor
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
        monthly_target_usd = initial_capital * 0.14
        df = df.sort_values("Datetime").reset_index(drop=True)

        df["Cumulative_USD"] = initial_capital + df["USD"].cumsum()
        current_equity = df["Cumulative_USD"].iloc[-1]
        pct_change = ((current_equity - initial_capital)/initial_capital)*100

        col9, col10 = st.columns(2)
        col9.metric("Equity actual", f"{round(current_equity,2)} USD", f"{round(pct_change,2)}% vs. inicio")
        target_equity = initial_capital + monthly_target_usd
        distance_to_target = target_equity - current_equity
        if distance_to_target > 0:
            dist_text = f"{round(distance_to_target,2)} USD"
        else:
            dist_text = "Meta superada!"
        col10.metric("Dist. a +14%", dist_text)

        # Pie Chart Win/Loss/BE
        fig_pie = px.pie(
            names=["Win","Loss","BE"],
            values=[wins, losses, be],
            title="Distribución Win / Loss / BE"
        )
        st.plotly_chart(fig_pie, use_container_width=True)

        # Objetivos en R
        risk_amount = initial_capital * 0.0025
        total_R_acum = net_profit / risk_amount
        R_faltantes = (monthly_target_usd - net_profit) / risk_amount
        trades_13_faltan = max(0, int(np.ceil(R_faltantes / 3))) if R_faltantes > 0 else 0

        st.write(f"**R's acumuladas**: {round(total_R_acum,2)}")
        st.write(f"**R's faltantes** para objetivo +14%: {round(R_faltantes,2)}")
        st.write(f"Trades 1:3 necesarios aprox: {trades_13_faltan}")

        # Evolución de la cuenta (gráfica)
        fig_line = px.line(
            df, 
            x="Datetime", 
            y="Cumulative_USD", 
            title="Evolución de la cuenta (USD Neto)"
        )
        st.plotly_chart(fig_line, use_container_width=True)

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
        st.write("Selecciona el índice del trade (0-based) para editar/borrar.")
        selected_idx = st.number_input(
            "Índice del trade",
            min_value=0, 
            max_value=df.shape[0] - 1,
            step=1
        )
        selected_row = df.loc[selected_idx].to_dict()
        st.write("Trade seleccionado:")
        st.json(selected_row)

        # Botón Borrar
        if st.button("Borrar este trade"):
            df = df.drop(selected_idx).reset_index(drop=True)
            # Como borramos una fila, REESCRIBIMOS todo el DF a la hoja
            overwrite_sheet(df)
            st.success("Trade borrado con éxito.")
            df = get_all_trades()  # Recargamos

        # Edición de campos (ACTUALIZA SOLO LA FILA)
        with st.form("edit_form"):
            st.write("Editar este trade:")

            new_fecha = st.text_input("Fecha", value=str(selected_row["Fecha"]))
            new_hora = st.text_input("Hora", value=str(selected_row["Hora"]))
            new_symbol = st.text_input("Symbol", value=str(selected_row["Symbol"]))
            new_type = st.text_input("Type", value=str(selected_row["Type"]))
            new_volume = st.number_input("Volume (lotes)", min_value=0.0, value=float(selected_row["Volume"]), step=0.01)
            new_result = st.text_input("Win/Loss/BE", value=str(selected_row["Win/Loss/BE"]))

            new_gross_usd = st.number_input("Gross USD", value=float(selected_row["Gross_USD"]), step=0.01)
            new_screenshot = st.text_input("Screenshot", value=str(selected_row["Screenshot"]))
            new_comments = st.text_area("Comentarios", value=str(selected_row["Comentarios"]))
            new_post_analysis = st.text_area("Post-Analysis", value=str(selected_row["Post-Analysis"]))

            submitted = st.form_submit_button("Guardar Cambios")
            if submitted:
                updated_commission = new_volume * 4.0
                updated_net_usd = new_gross_usd - updated_commission
                updated_r = calculate_r(updated_net_usd, account_size=60000, risk_percent=0.25)

                df.loc[selected_idx, "Fecha"]         = new_fecha
                df.loc[selected_idx, "Hora"]          = new_hora
                df.loc[selected_idx, "Symbol"]        = new_symbol
                df.loc[selected_idx, "Type"]          = new_type
                df.loc[selected_idx, "Volume"]        = new_volume
                df.loc[selected_idx, "Win/Loss/BE"]   = new_result
                df.loc[selected_idx, "Gross_USD"]     = new_gross_usd
                df.loc[selected_idx, "Commission"]    = updated_commission
                df.loc[selected_idx, "USD"]           = updated_net_usd
                df.loc[selected_idx, "R"]             = updated_r
                df.loc[selected_idx, "Screenshot"]    = new_screenshot
                df.loc[selected_idx, "Comentarios"]   = new_comments
                df.loc[selected_idx, "Post-Analysis"] = new_post_analysis

                # Construimos un dict con estos valores para actualizar UNA SOLA FILA en la hoja
                trade_dict_updated = df.loc[selected_idx].to_dict()
                update_single_row_in_sheet(selected_idx, trade_dict_updated)

                st.success("Trade editado con éxito.")
                # Recargamos df
                df = get_all_trades()

# Fin de la app
