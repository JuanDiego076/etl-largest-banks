"""
ETL de los 10 bancos más grandes del mundo por capitalización de mercado.

Extrae la tabla "By market capitalization" de una versión archivada de
Wikipedia, convierte la capitalización de USD a GBP, EUR e INR usando un CSV
de tipos de cambio, y carga el resultado en un CSV y en una base SQLite.
Cada etapa queda registrada en code_log.txt.

Uso:
    python banks_project.py
"""

import os
import sqlite3
from datetime import datetime

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
URL = "https://web.archive.org/web/20230908091635/https://en.wikipedia.org/wiki/List_of_largest_banks"
EXCHANGE_RATE_URL = (
    "https://cf-courses-data.s3.us.cloud-object-storage.appdomain.cloud/"
    "IBMSkillsNetwork-PY0221EN-Coursera/labs/v2/exchange_rate.csv"
)
EXCHANGE_RATE_PATH = "./exchange_rate.csv"
TABLE_ATTRIBS = ["Name", "MC_USD_Billion"]
OUTPUT_CSV_PATH = "./Largest_banks_data.csv"
DB_NAME = "Banks.db"
TABLE_NAME = "Largest_banks"
LOG_FILE = "code_log.txt"
REQUEST_TIMEOUT = 30  # segundos

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)


# ---------------------------------------------------------------------------
# Funciones ETL
# ---------------------------------------------------------------------------
def log_progress(message):
    """Registra el mensaje con su marca de tiempo en LOG_FILE."""
    timestamp = datetime.now().strftime("%Y-%h-%d-%H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{timestamp} : {message}\n")


def extract(url, table_attribs):
    """Extrae la tabla de capitalización de mercado y la devuelve como DataFrame."""
    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()  # falla de forma explícita ante 4xx/5xx

    soup = BeautifulSoup(response.text, "html.parser")
    tables = soup.find_all("tbody")
    if not tables:
        raise ValueError("No se encontró ninguna tabla en la página.")

    records = []
    for row in tables[0].find_all("tr"):
        col = row.find_all("td")
        if len(col) == 0:  # fila de encabezado
            continue
        links = col[1].find_all("a")
        # El segundo enlace es el del banco; el primero es la bandera del país
        name = links[1]["title"] if len(links) > 1 else col[1].get_text(strip=True)
        market_cap = float(col[2].get_text(strip=True).replace(",", ""))
        records.append({"Name": name, "MC_USD_Billion": market_cap})

    if not records:
        raise ValueError("La tabla no contiene filas de datos.")

    return pd.DataFrame(records, columns=table_attribs)


def load_exchange_rates(csv_path, fallback_url):
    """Lee el CSV de tipos de cambio local; si no existe, lo lee desde la URL."""
    source = csv_path if os.path.exists(csv_path) else fallback_url
    rates_df = pd.read_csv(source)
    return rates_df.set_index("Currency").to_dict()["Rate"]


def transform(df, exchange_rate):
    """Agrega columnas de capitalización en GBP, EUR e INR, redondeadas a 2 decimales."""
    df = df.copy()
    for currency in ("GBP", "EUR", "INR"):
        rate = float(exchange_rate[currency])
        df[f"MC_{currency}_Billion"] = np.round(df["MC_USD_Billion"] * rate, 2)
    return df


def load_to_csv(df, output_path):
    """Guarda el DataFrame final como CSV."""
    df.to_csv(output_path, index=False)


def load_to_db(df, sql_connection, table_name):
    """Guarda el DataFrame final como tabla; reemplaza la tabla si ya existe."""
    df.to_sql(table_name, sql_connection, if_exists="replace", index=False)


def run_query(query_statement, sql_connection):
    """Ejecuta la consulta e imprime la sentencia y su resultado."""
    print(query_statement)
    print(pd.read_sql(query_statement, sql_connection), "\n")


# ---------------------------------------------------------------------------
# Orquestación
# ---------------------------------------------------------------------------
def main():
    log_progress("Preliminares completos. Iniciando proceso ETL")

    try:
        df = extract(URL, TABLE_ATTRIBS)
        log_progress("Extracción de datos completa. Iniciando proceso de Transformación")

        exchange_rate = load_exchange_rates(EXCHANGE_RATE_PATH, EXCHANGE_RATE_URL)
        df = transform(df, exchange_rate)
        log_progress("Transformación de datos completa. Iniciando proceso de Carga")

        load_to_csv(df, OUTPUT_CSV_PATH)
        log_progress("Datos guardados en archivo CSV")

        sql_connection = sqlite3.connect(DB_NAME)
        log_progress("Conexión SQL iniciada")
        try:
            load_to_db(df, sql_connection, TABLE_NAME)
            log_progress("Datos cargados en la base de datos como una tabla, ejecutando consultas")

            run_query(f"SELECT * FROM {TABLE_NAME}", sql_connection)
            run_query(f"SELECT AVG(MC_GBP_Billion) FROM {TABLE_NAME}", sql_connection)
            run_query(f"SELECT Name FROM {TABLE_NAME} LIMIT 5", sql_connection)
            log_progress("Proceso completo")
        finally:
            sql_connection.close()  # se cierra aunque falle la carga o una consulta
            log_progress("Conexión al servidor cerrada")

    except requests.RequestException as e:
        log_progress(f"ERROR de red durante la extracción: {e}")
        raise
    except (ValueError, KeyError, IndexError) as e:
        log_progress(f"ERROR procesando los datos: {e}")
        raise


if __name__ == "__main__":
    main()
