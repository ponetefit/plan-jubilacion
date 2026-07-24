import json, datetime, pytz, yfinance as yf

TICKERS = {
    "AMZN": "AMZN.BA", "WMT": "WMT.BA", "GOOGL": "GOOGL.BA",
    "VIST": "VIST.BA", "KO": "KO.BA", "MO": "MO.BA",
    "O": "O.BA", "SPY": "SPY.BA", "RSP": "RSP.BA", "VWO": "VWO.BA"
}

precios = {}
for nombre, ticker in TICKERS.items():
    try:
        precio = yf.Ticker(ticker).fast_info.last_price
        if precio and precio > 0:
            precios[nombre] = round(float(precio), 2)
            print(f"{nombre}: {precio}")
    except Exception as e:
        print(f"{nombre}: error - {e}")

ahora = datetime.datetime.now(pytz.timezone("America/Argentina/Buenos_Aires")).strftime("%d/%m/%Y %H:%M")
json.dump({"fecha": ahora, "moneda": "ARS", "fuente": "Yahoo Finance · BYMA", "precios_ars": precios},
          open("precios_cedears.json", "w"), ensure_ascii=False, indent=2)
print(f"Listo: {len(precios)} precios — {ahora}")
