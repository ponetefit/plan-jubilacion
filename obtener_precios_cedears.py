import json
import datetime
import pytz
import yfinance as yf

TICKERS = {
    "AMZN": "AMZN.BA",
    "WMT":  "WMT.BA",
    "GOOGL":"GOOGL.BA",
    "VIST": "VIST.BA",
    "KO":   "KO.BA",
    "MO":   "MO.BA",
    "O":    "O.BA",
    "SPY":  "SPY.BA",
    "RSP":  "RSP.BA",
    "VWO":  "VWO.BA"
}

precios = {}
for nombre, ticker_ba in TICKERS.items():
    try:
        data = yf.Ticker(ticker_ba).fast_info
        precio = data.last_price
        if precio and precio > 0:
            precios[nombre] = round(float(precio), 2)
    except Exception as e:
        print(f"  {nombre}: error — {e}")

tz_ar = pytz.timezone("America/Argentina/Buenos_Aires")
ahora = datetime.datetime.now(tz_ar).strftime("%d/%m/%Y %H:%M")

resultado = {
    "fecha": ahora,
    "moneda": "ARS",
    "fuente": "Yahoo Finance · BYMA",
    "precios_ars": precios
}

with open("precios_cedears.json", "w", encoding="utf-8") as f:
    json.dump(resultado, f, ensure_ascii=False, indent=2)

print(f"Listo: {len(precios)} precios guardados — {ahora}")
