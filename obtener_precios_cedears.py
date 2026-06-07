#!/usr/bin/env python3
"""
obtener_precios_cedears.py
==========================
Extrae los precios actuales de 10 CEDEARs desde Yahoo Finance
(datos de BYMA, en pesos ARS — sin instalar nada extra).

Clave: los tickers SIN sufijo "D" en Yahoo Finance (.BA) devuelven
precios en ARS. Los que terminan en "D" cotizan en USD (cable).

Uso:
    python obtener_precios_cedears.py
    python obtener_precios_cedears.py --html mi_retiro_2036.html

Requisitos: Python 3.9+ — solo stdlib, sin pip
"""

import argparse
import gzip
import http.cookiejar
import json
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

# ─── TIMEZONE ─────────────────────────────────────────────────────────────────
try:
    from zoneinfo import ZoneInfo
    TZ_ARG = ZoneInfo("America/Argentina/Buenos_Aires")
except Exception:
    TZ_ARG = timezone(timedelta(hours=-3))   # UTC-3, sin DST

# ─── TICKERS ──────────────────────────────────────────────────────────────────
# Regla de Yahoo Finance para BYMA:
#   SIN "D" al final  →  cotización en ARS  ← queremos este
#   CON "D" al final  →  cotización en USD (dólar cable)
#
# Cada ticker tiene una lista de candidatos en orden de prioridad.
# El script prueba el primero que devuelva precio en ARS.

SYMBOLS: dict[str, list[str]] = {
    "AMZN":  ["AMZN.BA",  "AMZND.BA"],
    "WMT":   ["WMT.BA",   "WMTD.BA"],
    "GOOGL": ["GOOGL.BA", "GOOG.BA"],
    "VIST":  ["VIST.BA",  "VISTD.BA"],
    "KO":    ["KO.BA",    "KOD.BA"],
    "MO":    ["MO.BA",    "MOD.BA"],
    "O":     ["O.BA",     "OD.BA"],
    "SPY":   ["SPY.BA",   "SPYD.BA"],
    "RSP":   ["RSP.BA",   "RSPD.BA"],
    "VWO":   ["VWO.BA",   "VWOD.BA"],
}

DEFAULT_HTML = "mi_retiro_2036.html"
JSON_OUTPUT  = "precios_cedears.json"

# ─── SSL ──────────────────────────────────────────────────────────────────────

def _ssl_context() -> ssl.SSLContext:
    """Intenta con verificación; si falla (Windows sin certs) usa sin verificar."""
    try:
        ctx = ssl.create_default_context()
        if not ctx.get_ca_certs():
            raise ValueError("sin certs")
        return ctx
    except Exception:
        return ssl._create_unverified_context()


# ─── YAHOO FINANCE — HTTP SESSION CON COOKIE + CRUMB ──────────────────────────

class YahooSession:
    """
    Replica el handshake que hace yfinance:
    1. GET fc.yahoo.com  →  recibe cookie de sesión
    2. GET getcrumb      →  recibe token de 1 sola cadena
    3. Incluye cookie + crumb en cada consulta de precios
    """

    BASE_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept":          "application/json, */*",
        "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
    }

    def __init__(self) -> None:
        ssl_ctx = _ssl_context()
        jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar),
            urllib.request.HTTPSHandler(context=ssl_ctx),
        )
        self.crumb: str | None = None

    def _get(self, url: str) -> str:
        req = urllib.request.Request(url, headers=self.BASE_HEADERS)
        with self._opener.open(req, timeout=20) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding", "") == "gzip":
                raw = gzip.decompress(raw)
            enc = r.headers.get_content_charset("utf-8")
            return raw.decode(enc)

    def init(self) -> None:
        """Obtiene cookie y crumb de Yahoo Finance."""
        # Paso 1: cookie
        for base in ["https://fc.yahoo.com", "https://finance.yahoo.com"]:
            try:
                self._get(base)
                break
            except Exception:
                continue

        # Paso 2: crumb
        for host in ["query2", "query1"]:
            try:
                crumb = self._get(
                    f"https://{host}.finance.yahoo.com/v1/test/getcrumb"
                ).strip()
                if crumb and crumb != "":
                    self.crumb = crumb
                    return
            except Exception:
                continue

        # Si falla el crumb, seguimos igual (puede que no sea necesario)
        self.crumb = ""

    def quote_bulk(self, symbols: list[str]) -> dict[str, dict]:
        """
        Devuelve {symbol: {"price": float, "currency": str, "name": str}}
        para todos los símbolos que responden.
        """
        params: dict[str, str] = {
            "symbols": ",".join(symbols),
            "fields":  "regularMarketPrice,currency,shortName",
            "lang":    "en-US",
            "region":  "US",
        }
        if self.crumb:
            params["crumb"] = self.crumb

        for host in ["query1", "query2"]:
            url = f"https://{host}.finance.yahoo.com/v7/finance/quote?{urllib.parse.urlencode(params)}"
            try:
                raw  = self._get(url)
                data = json.loads(raw)
                items = data.get("quoteResponse", {}).get("result", [])
                result: dict[str, dict] = {}
                for x in items:
                    sym   = x.get("symbol", "")
                    price = x.get("regularMarketPrice")
                    cur   = x.get("currency", "").upper()
                    name  = x.get("shortName", "")
                    if sym and price and float(price) > 0:
                        result[sym] = {
                            "price":    round(float(price), 2),
                            "currency": cur,
                            "name":     name,
                        }
                return result
            except urllib.error.HTTPError as e:
                if e.code in (401, 403, 406):
                    # Intentar con el otro host
                    continue
                raise
        return {}

    def quote_single(self, symbol: str) -> dict | None:
        """Fallback individual usando la API de chart."""
        params: dict[str, str] = {"interval": "1d", "range": "1d"}
        if self.crumb:
            params["crumb"] = self.crumb

        for host in ["query1", "query2"]:
            url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}?{urllib.parse.urlencode(params)}"
            try:
                raw  = self._get(url)
                data = json.loads(raw)
                meta = (
                    data.get("chart", {})
                        .get("result", [{}])[0]
                        .get("meta", {})
                )
                price = meta.get("regularMarketPrice") or meta.get("previousClose")
                cur   = meta.get("currency", "").upper()
                if price and float(price) > 0:
                    return {
                        "price":    round(float(price), 2),
                        "currency": cur,
                        "name":     meta.get("shortName", ""),
                    }
            except Exception:
                continue
        return None


# ─── LÓGICA PRINCIPAL ─────────────────────────────────────────────────────────

def obtener_precios(session: YahooSession) -> dict[str, float]:
    """
    Para cada ticker del portafolio, prueba candidatos .BA en orden
    y acepta el primero que devuelva precio en ARS.
    """
    todos = [sym for variantes in SYMBOLS.values() for sym in variantes]

    print("  → Yahoo Finance (bulk)...", end=" ", flush=True)
    bulk = session.quote_bulk(todos)
    n_ok = sum(1 for v in bulk.values() if v["currency"] == "ARS")
    print(f"✓  ({len(bulk)} cotizaciones, {n_ok} en ARS)")

    precios:  dict[str, float] = {}
    moneda_d: list[str]        = []   # tickers que solo devolvieron USD

    for ticker, variantes in SYMBOLS.items():
        elegido = False
        for sym in variantes:
            if sym not in bulk:
                continue
            info = bulk[sym]
            if info["currency"] == "ARS":
                precios[ticker] = info["price"]
                elegido = True
                break
            # Es USD → guardar por si no hay alternativa ARS
            moneda_d.append(f"{sym}(USD)")

        if not elegido:
            # Intento individual
            for sym in variantes:
                info = session.quote_single(sym)
                if info and info["currency"] == "ARS":
                    precios[ticker] = info["price"]
                    elegido = True
                    break

        if not elegido:
            pass  # Se mostrará como "sin dato" en la tabla

    if moneda_d:
        print(f"\n  ℹ  Ignorados (cotizan en USD, no ARS): {', '.join(moneda_d)}")

    return precios


# ─── ACTUALIZAR HTML ──────────────────────────────────────────────────────────

def actualizar_html(html_path: str, precios: dict[str, float], fecha: str) -> None:
    with open(html_path, encoding="utf-8") as f:
        lines = f.readlines()

    actualizadas = 0
    resultado: list[str] = []

    for line in lines:
        nueva = line
        for ticker, precio in precios.items():
            if (
                re.match(rf"\s+{re.escape(ticker)}\s*:", line)
                and "precioMercadoARS" in line
            ):
                nueva, n = re.subn(
                    r"(precioMercadoARS:\s*)\d+(?:\.\d+)?",
                    rf"\g<1>{precio:.2f}",
                    line,
                )
                if n:
                    actualizadas += 1
                break

        if 'id="last-update-time"' in nueva:
            nueva, _ = re.subn(
                r'(id="last-update-time"[^>]*>)[^<]*(</span>)',
                rf"\g<1>Precios: En vivo {fecha}\2",
                nueva,
            )

        resultado.append(nueva)

    if actualizadas == 0:
        raise ValueError(
            f"No se actualizó ningún precio en '{html_path}'. "
            "Verificá que sea el archivo correcto."
        )

    with open(html_path, "w", encoding="utf-8") as f:
        f.writelines(resultado)

    print(f"  ✓  {actualizadas} precio(s) actualizado(s) en '{html_path}'")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Obtiene precios de CEDEARs en ARS desde Yahoo Finance y actualiza el HTML."
    )
    parser.add_argument("--html", default=DEFAULT_HTML,
                        help=f"Ruta al HTML (default: {DEFAULT_HTML})")
    args = parser.parse_args()

    SEP = "═" * 64
    print(f"\n{SEP}")
    print("  Mi Retiro 2036 · Actualizador de precios CEDEAR (ARS)")
    print(f"{SEP}")

    # ── 1. Iniciar sesión Yahoo Finance ───────────────────────────────────────
    print("\n[1/3] Iniciando sesión con Yahoo Finance...")
    session = YahooSession()
    try:
        session.init()
        estado = f"crumb={'✓' if session.crumb else 'no requerido'}"
        print(f"  ✓  Conexión establecida ({estado})")
    except Exception as e:
        print(f"  ⚠  Sin crumb ({e}) — se intenta igual")

    # ── 2. Obtener precios ────────────────────────────────────────────────────
    print("\n[2/3] Consultando precios en ARS...")
    try:
        precios = obtener_precios(session)
    except Exception as e:
        print(f"\n  ✗  Error: {e}")
        sys.exit(1)

    if not precios:
        print("  ✗  No se obtuvo ningún precio en ARS.")
        print("     Verificá tu conexión a internet y volvé a intentar.")
        sys.exit(1)

    # ── Tabla ─────────────────────────────────────────────────────────────────
    ahora = datetime.now(tz=TZ_ARG)
    fecha = ahora.strftime("%d/%m/%Y %H:%M")

    print(f"\n  Precios al {fecha} hs (hora Argentina)\n")
    print(f"  {'Ticker':<8}  {'Yahoo (.BA)':<14}  {'Precio ARS':>16}")
    print("  " + "─" * 42)
    for ticker, variantes in SYMBOLS.items():
        sym_ars = variantes[0]
        precio  = precios.get(ticker)
        if precio is not None:
            print(f"  {ticker:<8}  {sym_ars:<14}  $ {precio:>12,.2f}")
        else:
            print(f"  {ticker:<8}  {sym_ars:<14}  {'⚠ Sin dato':>15}")

    encontrados = len(precios)
    print(f"\n  Encontrados: {encontrados}/10 CEDEARs en ARS")
    if encontrados < 10:
        faltantes = [t for t in SYMBOLS if t not in precios]
        print(f"  Sin dato:    {', '.join(faltantes)}")
        print("  (Puede que no coticen en BYMA o estén fuera de horario)")

    # ── 3. Guardar JSON ───────────────────────────────────────────────────────
    with open(JSON_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(
            {
                "fecha":       fecha,
                "moneda":      "ARS",
                "fuente":      "Yahoo Finance · BYMA",
                "tickers_ba":  {t: SYMBOLS[t][0] for t in SYMBOLS},
                "precios_ars": precios,
            },
            f, ensure_ascii=False, indent=2,
        )
    print(f"\n  ✓  Guardado → {JSON_OUTPUT}")

    # ── 4. Actualizar HTML ────────────────────────────────────────────────────
    if precios:
        print(f"\n[3/3] Actualizando {args.html}...")
        try:
            actualizar_html(args.html, precios, fecha)
        except FileNotFoundError:
            print(
                f"  ⚠  '{args.html}' no encontrado.\n"
                f"     Usá:  python obtener_precios_cedears.py --html /ruta/al/archivo.html"
            )
        except ValueError as e:
            print(f"  ✗  {e}")

    print(f"\n{SEP}")
    print(f"  Completado — {fecha} hs (Argentina)")
    print(f"{SEP}\n")


if __name__ == "__main__":
    main()
