#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
 Herramienta de reconocimiento web (Fase 1)
 Trabajo Fin de Grado
============================================================================
 Este script automatiza la primera fase la metodología:
 el RECONOCIMIENTO. Dada una URL base, descubre rutas y endpoints expuestos
 por el sitio (páginas, APIs, documentación Swagger...) y genera un informe
 en JSON y HTML con los resultados.

 Técnicas empleadas (todas PASIVAS y NO INTRUSIVAS):
   1. Lectura del HTML y extracción de enlaces (<a>, <form>, <link>).
   2. Análisis estático de JavaScript mediante expresiones regulares.
   3. Detección automática de documentación.
   4. Comprobación de rutas comunes (/admin, /login, /api, /robots.txt...).
   5. Crawler en anchura (BFS) con profundidad y tope de URLs limitados.

 Uso legítimo: SOLO sobre objetivos para los que se tenga autorización
 explícita del propietario. El uso indebido es responsabilidad del usuario.
============================================================================
"""


import argparse                              # define y parsea argumentos de línea de comandos
import json                                  # convierte diccionarios de Python a JSON y viceversa
import re                                    # expresiones regulares: buscar patrones en texto
import sys                                   # acceso a stderr para imprimir errores
import time                                  # sleep() para limitar la velocidad de peticiones
from collections import deque                # deque = double-ended queue, ideal para BFS
from datetime import datetime                # fecha y hora actuales (para generar el informe)
from urllib.parse import urljoin, urlparse   # utilidades para manipular URLs

import requests                              # librería externa: hacer peticiones HTTP cómodamente
from bs4 import BeautifulSoup                # librería externa: parsear HTML


# =========================================================================
# CONFIGURACIÓN GLOBAL
# =========================================================================


# Tiempo máximo (en segundos) que se espera una respuesta del servidor antes
# de abortar la petición. Evita que el script se quede colgado si un sitio
# tarda demasiado o no responde.
DEFAULT_TIMEOUT = 8

# User-Agent: cadena que identifica a nuestro cliente ante el servidor.

USER_AGENT = "ReconTool/1.0 (+educational)"

# Lista de rutas comunes que probaremos en cualquier sitio.

COMMON_PATHS = [
    "/", "/robots.txt", "/sitemap.xml", "/humans.txt",
    "/api", "/api/", "/api/v1", "/api/v2", "/api/users",
    "/users", "/login", "/admin", "/dashboard", "/health",
    "/status", "/swagger", "/swagger.json", "/swagger-ui.html",
    "/docs", "/openapi.json", "/graphql", "/.well-known/security.txt",
]

# Expresiones regulares (regex) que detectan endpoints dentro de código JS.
#
JS_ENDPOINT_PATTERNS = [
    # Captura lo que está entre comillas dentro de fetch("..."):
    re.compile(r"""fetch\(\s*["'`]([^"'`]+)["'`]"""),
    # Captura la URL de llamadas axios.get/post/put/delete/patch:
    re.compile(r"""axios\.(?:get|post|put|delete|patch)\(\s*["'`]([^"'`]+)["'`]"""),
    # Captura la URL dentro de $.ajax({url:"..."}):
    re.compile(r"""\.ajax\(\s*\{[^}]*url\s*:\s*["'`]([^"'`]+)["'`]"""),
    # Cualquier cadena que empiece por "/" y parezca una ruta (heurística):
    re.compile(r"""["'`](/[a-zA-Z0-9_\-/]+(?:\.[a-zA-Z0-9]+)?)["'`]"""),
    # URLs absolutas (http:// o https://):
    re.compile(r"""["'`](https?://[^"'`\s]+)["'`]"""),
]


# =========================================================================
# FUNCIONES AUXILIARES
# =========================================================================
# Funciones pequeñas con una sola responsabilidad. 
# -------------------------------------------------------------------------

def new_session() -> requests.Session:
    """
    Crea una sesión HTTP reutilizable.

    Una 'Session' mantiene viva la conexión TCP entre peticiones al mismo
    servidor (HTTP keep-alive), lo que es más rápido y más cortés con el
    objetivo que abrir una conexión nueva para cada URL.
    """
    s = requests.Session()                          # instanciamos la sesión
    s.headers.update({"User-Agent": USER_AGENT})    # aplicamos nuestro User-Agent a todas las peticiones
    return s


def fetch(session: requests.Session, url: str) -> requests.Response | None:
    """
    Descarga una URL de forma segura.

    Se usa para recursos auxiliares (ficheros JS, OpenAPI...), donde nos
    basta con el contenido y no necesitamos registrar metadatos detallados.
    Si la petición falla (timeout, DNS, error SSL, etc.) devuelve None en
    lugar de lanzar una excepción, para que el script continúe.
    """
    try:
        # allow_redirects=True → si el servidor responde 301/302, seguimos la redirección.
        # timeout → si tarda más de DEFAULT_TIMEOUT segundos, cancela la petición.
        return session.get(url, timeout=DEFAULT_TIMEOUT, allow_redirects=True)
    except requests.RequestException as e:
        print(f"[!] Error en {url}: {e}", file=sys.stderr)
        return None


def extract_links_from_html(html: str, base_url: str) -> tuple[set[str], set[str]]:
    """
    Extrae enlaces y scripts de un documento HTML.

    Devuelve DOS conjuntos (sets):
      - links:   URLs de páginas que podríamos visitar después.
      - scripts: URLs de ficheros JavaScript que analizaremos con regex.
    """
    # html.parser es el parser incluido en Python. No requiere instalar 'lxml'.
    soup = BeautifulSoup(html, "html.parser")
    links, scripts = set(), set()

    # <a href="..."> → enlaces normales
    for tag in soup.find_all("a", href=True):
        links.add(urljoin(base_url, tag["href"]))

    # <link> y <form> también pueden apuntar a recursos interesantes
    for tag in soup.find_all(["link", "form"]):
        ref = tag.get("href") or tag.get("action")   # link usa href, form usa action
        if ref:
            links.add(urljoin(base_url, ref))

    # <script src="..."> → ficheros JS para analizar después
    for tag in soup.find_all("script", src=True):
        scripts.add(urljoin(base_url, tag["src"]))

    return links, scripts


def extract_endpoints_from_js(js_code: str) -> set[str]:
    """
    Busca endpoints dentro del código fuente de un fichero JavaScript.

    Aplica cada regex definida en JS_ENDPOINT_PATTERNS y acumula los
    resultados en un set (para deduplicar automáticamente).
    """
    found = set()
    for pattern in JS_ENDPOINT_PATTERNS:
        # findall() devuelve TODAS las coincidencias como una lista de cadenas.
        for match in pattern.findall(js_code):
            # Filtramos "pseudo-URLs" que no son endpoints reales:
            #   data:image/png;base64,...    (imagen embebida)
            #   blob:...                     (referencia a objeto en memoria)
            #   mailto:info@ejemplo.com      (dirección de correo)
            #   tel:+34...                   (número de teléfono)
            if match and not match.startswith(("data:", "blob:", "mailto:", "tel:")):
                found.add(match)
    return found


def same_host(url: str, base: str) -> bool:
    """
    Comprueba si una URL pertenece al mismo dominio que la URL base.

    Esta función es la SALVAGUARDA más importante del crawler: evita que
    el script se salga del objetivo y empiece a escanear terceros (lo cual
    sería abusivo y probablemente ilegal).
    """
    try:
        return urlparse(url).netloc in ("", urlparse(base).netloc)
    except Exception:
        # Si urlparse falla por un formato muy extraño, jugamos seguro: False.
        return False


def probe(session: requests.Session, url: str) -> tuple[dict, requests.Response | None]:
    """
    Consulta un endpoint concreto y extrae sus metadatos.

    Devuelve record, response:
      - record:   diccionario con los datos que guardaremos en el informe.
      - response: objeto Response completo, por si el crawler quiere leer
                  el cuerpo para seguir explorando enlaces dentro.
    """
    # Preparamos un diccionario con todos los campos a None.
    record = {
        "url": url,
        "method": "GET",
        "status": None,
        "content_type": None,
        "length": None,
        "headers": {},
        "error": None,
    }
    try:
        r = session.get(url, timeout=DEFAULT_TIMEOUT, allow_redirects=True)
        record["status"] = r.status_code                    # ej. 200, 404, 500
        record["content_type"] = r.headers.get("Content-Type")  # "text/html", "application/json"...
        record["length"] = len(r.content)                   
        record["headers"] = dict(r.headers)                
        record["final_url"] = r.url                         # URL final después de redirects
        return record, r
    except requests.RequestException as e:
        # Si hay error de red, guardamos el mensaje y devolvemos None como respuesta.
        record["error"] = str(e)
        return record, None

def check_swagger(session: requests.Session, base: str) -> dict | None:
    """Busca documentación de API en rutas estándar de OpenAPI/Swagger."""
    for path in ("/openapi.json", "/swagger.json", "/v2/api-docs", "/v3/api-docs"):
        url = urljoin(base, path)
        r = fetch(session, url)
        if r is not None and r.status_code == 200:
            try:
                data = r.json()
                paths = list(data.get("paths", {}).keys())
                return {"source": url, "paths": paths}
            except ValueError:
                # No era JSON válido → probamos la siguiente ruta
                continue
    return None


# =========================================================================
# FUNCIÓN PRINCIPAL DE RECONOCIMIENTO (crawler BFS limitado)
# =========================================================================
# BFS = Breadth-First Search (búsqueda en anchura). Exploramos nivel a nivel:
# primero la raíz, luego todos sus hijos, luego todos los nietos, etc.
#
# Por qué BFS y no DFS (profundidad):
#   - BFS encuentra primero las páginas "cercanas", que suelen ser las más
#     importantes (home, secciones principales).
#   - Con un límite de URLs, BFS garantiza una cobertura amplia en lugar de
#     hundirse por una sola rama.
# -------------------------------------------------------------------------
def recon(base_url: str, max_depth: int = 1, max_urls: int = 200,
          delay: float = 0.2, max_js: int = 10) -> dict:
    """
    Ejecuta el proceso completo de reconocimiento.

    Parámetros:
      base_url:  URL inicial del objetivo.
      max_depth: niveles de profundidad del crawler (0 = solo la raíz).
      max_urls:  tope absoluto de URLs a visitar. SEGURIDAD anti-runaway.
      delay:     segundos de espera entre peticiones (rate limit).
      max_js:    número máximo de ficheros JS a analizar en total.
    """
    session = new_session()

    # -------------------- Estructura del informe --------------------
    # Usamos un diccionario porque se serializa trivialmente a JSON.
    # datetime.utcnow().isoformat() nos da una fecha estándar ISO 8601 (UTC).
    report = {
        "target": base_url,
        "generated_at": datetime.utcnow().isoformat() + "Z",  # la "Z" indica UTC
        "config": {"max_depth": max_depth, "max_urls": max_urls, "delay": delay},
        "discovered_urls": [],
        "probed": [],
        "openapi": None,
    }

    # -------------------- Semillas iniciales de la cola BFS --------------------
    # Cada elemento de la cola es una tupla (url, profundidad).
    # Usamos deque en vez de list porque popleft() es O(1), mientras que
    # list.pop(0) sería O(n) (mover todos los elementos).
    queue: deque[tuple[str, int]] = deque()

    # Semilla 1: la URL raíz del objetivo, a profundidad 0.
    queue.append((base_url, 0))

    # Semilla 2: las rutas comunes. Las sembramos también a profundidad 0.
    # Si max_depth es 0, solo se probarán (no expandirán). Si es >0, sus
    # enlaces también se explorarán.
    for path in COMMON_PATHS:
        queue.append((urljoin(base_url, path), 0))

    # Semilla 3: endpoints de Swagger/OpenAPI si el sitio los publica.
    swagger = check_swagger(session, base_url)
    if swagger:
        report["openapi"] = swagger
        for p in swagger["paths"]:
            queue.append((urljoin(base_url, p), 0))

    # -------------------- Estructuras de control del BFS --------------------
    visited: set[str] = set()   # URLs que ya hemos probado (no repetimos)
    js_seen: set[str] = set()   # ficheros JS ya descargados (no repetimos)
    js_count = 0                # cuántos JS llevamos (para respetar max_js)

    # -------------------- Bucle principal del crawler --------------------
    # Condición de parada DOBLE:
    #   - La cola se vacía (ya no hay más URLs que explorar), o
    #   - Hemos visitado el tope máximo de URLs (seguridad).
    while queue and len(visited) < max_urls:

        # popleft() saca el primer elemento de la cola → comportamiento FIFO → BFS
        url, depth = queue.popleft()

        # ---- Filtros de entrada: saltamos URLs no válidas ----
        if url in visited:
            # Ya la procesamos en una iteración anterior.
            continue
        if not same_host(url, base_url):
            # Pertenece a otro dominio: NO la visitamos (cuestión ética/legal).
            continue
        if not url.startswith(("http://", "https://")):
            # javascript:, data:, ftp:... no nos interesan.
            continue

        # Marcamos la URL como visitada ANTES de la petición, para evitar
        # que se añada a la cola dos veces durante el procesamiento actual.
        visited.add(url)

        # ---- Rate limit ----
        # Dormir entre peticiones reduce la carga sobre el servidor objetivo.
        # 0.2s por defecto equivale a un máximo de 5 peticiones por segundo.
        if delay > 0:
            time.sleep(delay)

        # ---- Petición y registro ----
        record, response = probe(session, url)
        report["probed"].append(record)

        # Feedback en consola para que el usuario vea el progreso en tiempo real.
        print(f"[{record.get('status','ERR')}] d={depth} {url}")

        # ---- Condiciones de NO expansión ----
        # No exploramos más a fondo si:
        #   - Hubo error de red (response is None).
        #   - Ya estamos en el nivel máximo de profundidad.
        if response is None or depth >= max_depth:
            continue

        # ---- Extracción de nuevos enlaces ----
        # Solo tiene sentido analizar el cuerpo si es HTML.
        # Accedemos a Content-Type de forma defensiva (puede no existir).
        content_type = (response.headers.get("Content-Type") or "").lower()

        if "html" in content_type:
            links, scripts = extract_links_from_html(response.text, base_url)

            # --- Enlaces HTML → encolar a profundidad+1 ---
            for link in links:
                if link not in visited and same_host(link, base_url):
                    queue.append((link, depth + 1))

            # --- Scripts JS → descargar y analizar ---
            for js_url in scripts:
                # Respetamos el tope global de JS (evita escanear cientos
                # de ficheros de librerías como jQuery o React).
                if js_count >= max_js:
                    break
                if js_url in js_seen:
                    continue
                js_seen.add(js_url)
                js_count += 1

                jr = fetch(session, js_url)
                if jr is not None and jr.status_code == 200:
                    # Buscamos endpoints dentro del JS y los encolamos.
                    for ep in extract_endpoints_from_js(jr.text):
                        full = urljoin(base_url, ep)
                        if full not in visited and same_host(full, base_url):
                            queue.append((full, depth + 1))

    # -------------------- Cierre del informe --------------------
    # sorted() para que el listado final sea legible y determinista.
    report["discovered_urls"] = sorted(visited)
    return report


# =========================================================================
# GENERADOR DE INFORME HTML
# =========================================================================
# Convertimos el diccionario del informe en una página HTML legible.
# Es una plantilla sencilla con CSS inline: no requiere ficheros externos
# y se puede abrir en cualquier navegador.
# -------------------------------------------------------------------------
def render_html(report: dict) -> str:
    """Genera un informe HTML con tabla coloreada según el código de estado."""
    rows = []

    # Una fila por cada URL probada.
    for r in report["probed"]:
        status = r.get("status") or "ERR"

        # Colores semafóricos según el primer dígito del status:
        #   2xx (éxito)         → verde
        #   3xx (redirección)   → amarillo
        #   4xx (error cliente) → naranja
        #   5xx (error servidor)→ rojo
        # El operador // es división entera: 200 // 100 = 2, 404 // 100 = 4.
        color = {2: "#c8e6c9", 3: "#fff9c4", 4: "#ffccbc", 5: "#ef9a9a"}.get(
            (r.get("status") or 0) // 100, "#eeeeee")

        rows.append(
            f"<tr style='background:{color}'>"
            f"<td>{r.get('url','')}</td>"
            f"<td>{status}</td>"
            f"<td>{r.get('content_type','') or ''}</td>"
            f"<td>{r.get('length','') or ''}</td>"
            f"</tr>"
        )

    # Sección opcional: paths declarados por Swagger/OpenAPI si existen.
    swagger_block = ""
    if report.get("openapi"):
        items = "".join(f"<li>{p}</li>" for p in report["openapi"]["paths"])
        swagger_block = f"<h2>OpenAPI ({report['openapi']['source']})</h2><ul>{items}</ul>"

    # Línea de configuración: importante para la trazabilidad del escaneo.
    cfg = report.get("config", {})
    cfg_line = (f"<b>Profundidad:</b> {cfg.get('max_depth','?')} · "
                f"<b>Máx URLs:</b> {cfg.get('max_urls','?')} · "
                f"<b>Delay:</b> {cfg.get('delay','?')}s")

    # Plantilla HTML final.
    # NOTA: dentro de un f-string, las llaves literales { } se escriben dobles {{ }}.
    # Por eso el CSS aparece con llaves dobles en el código fuente.
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Recon {report['target']}</title>
<style>
 body{{font-family:system-ui,sans-serif;margin:2rem;}}
 table{{border-collapse:collapse;width:100%;}}
 th,td{{border:1px solid #ddd;padding:.4rem .6rem;font-size:14px;}}
 th{{background:#263238;color:#fff;text-align:left;}}
</style></head>
<body>
<h1>Informe de reconocimiento</h1>
<p><b>Objetivo:</b> {report['target']}<br>
<b>Generado:</b> {report['generated_at']}<br>
{cfg_line}<br>
<b>URLs descubiertas:</b> {len(report['discovered_urls'])}</p>
{swagger_block}
<h2>Resultados</h2>
<table><tr><th>URL</th><th>Status</th><th>Content-Type</th><th>Bytes</th></tr>
{''.join(rows)}
</table></body></html>"""


# =========================================================================
# PUNTO DE ENTRADA (CLI)
# =========================================================================
# 'Interfaz de línea de comandos': procesamos los argumentos que el usuario
# escribe en la terminal y lanzamos el reconocimiento.
# -------------------------------------------------------------------------
def main() -> None:
    """Orquesta la ejecución: parsea argumentos, lanza el escaneo y guarda resultados."""

    # argparse construye automáticamente el --help y valida tipos.
    parser = argparse.ArgumentParser(description="Herramienta de reconocimiento (fase 1).")

    # --- Argumento posicional (obligatorio) ---
    parser.add_argument("url", help="URL base, p.ej. https://ejemplo.com")

    # --- Argumentos de salida ---
    parser.add_argument("-o", "--output", default="recon_report",
                        help="Prefijo de los archivos de salida (sin extensión).")
    parser.add_argument("--format", choices=["json", "html", "both"], default="both",
                        help="Formato del informe.")

    # --- Argumentos del crawler ---
    parser.add_argument("--depth", type=int, default=1,
                        help="Profundidad del crawler (0 = solo la raíz). Por defecto: 1.")
    parser.add_argument("--max-urls", type=int, default=200,
                        help="Tope máximo de URLs a visitar. Por defecto: 200.")
    parser.add_argument("--delay", type=float, default=0.2,
                        help="Segundos de espera entre peticiones. Por defecto: 0.2.")
    parser.add_argument("--max-js", type=int, default=10,
                        help="Máximo de scripts JS a analizar. Por defecto: 10.")

    # parse_args() lee sys.argv, valida, y convierte los valores a los tipos pedidos.
    args = parser.parse_args()

    # Validación extra: la URL debe incluir el esquema.
    if not args.url.startswith(("http://", "https://")):
        parser.error("La URL debe empezar por http:// o https://")

    # --- Ejecución ---
    print(f"[*] Reconociendo {args.url} (depth={args.depth}, max_urls={args.max_urls})")
    report = recon(
        args.url,
        max_depth=args.depth,
        max_urls=args.max_urls,
        delay=args.delay,
        max_js=args.max_js,
    )
    print(f"[+] {len(report['discovered_urls'])} URLs visitadas")

    # --- Escritura del JSON ---
    # 'with open(...)' asegura que el fichero se cierra correctamente aunque falle.
    if args.format in ("json", "both"):
        path = f"{args.output}.json"
        with open(path, "w", encoding="utf-8") as f:
            # indent=2 → formato legible con sangrado de 2 espacios.
            # ensure_ascii=False → conserva tildes y caracteres Unicode.
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"[+] JSON -> {path}")

    # --- Escritura del HTML ---
    if args.format in ("html", "both"):
        path = f"{args.output}.html"
        with open(path, "w", encoding="utf-8") as f:
            f.write(render_html(report))
        print(f"[+] HTML -> {path}")


# =========================================================================
# EJECUCIÓN
# =========================================================================
# Esta construcción es un IDIOMA estándar de Python.
# __name__ vale "__main__" solo cuando el fichero se ejecuta directamente
# (p.ej. 'python recon.py ...'). Si el fichero se importa desde otro script
# (p.ej. 'import recon'), __name__ valdrá "recon" y main() NO se ejecutará.
# Permite usar este archivo tanto como herramienta como librería.
# -------------------------------------------------------------------------
if __name__ == "__main__":
    main()
