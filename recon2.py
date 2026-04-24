#!/usr/bin/env python3

import argparse
import json
import re
import sys
import time
from collections import deque
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

DEFAULT_TIMEOUT = 8
USER_AGENT = "ReconTool/1.0"

COMMON_PATHS = [
    "/",
    "/robots.txt",
    "/sitemap.xml",
    "/humans.txt",
    "/api",
    "/api/",
    "/api/v1",
    "/api/v2",
    "/api/users",
    "/users",
    "/login",
    "/admin",
    "/dashboard",
    "/health",
    "/status",
    "/swagger",
    "/swagger.json",
    "/swagger-ui.html",
    "/docs",
    "/openapi.json",
    "/graphql",
    "/.well-known/security.txt",
]

JS_ENDPOINT_PATTERNS = [
    re.compile(r'fetch\(\s*["\']([^"\']+)["\']'),
    re.compile(r'axios\.(?:get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']'),
    re.compile(r'url\s*:\s*["\']([^"\']+)["\']'),
    re.compile(r'["\'](/api/[^"\']+)["\']'),
    re.compile(r'["\'](/v\d+/[^"\']+)["\']'),
    re.compile(r'["\'](https?://[^"\']+)["\']'),
]


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def fetch(session: requests.Session, url: str) -> requests.Response | None:
    try:
        return session.get(url, timeout=DEFAULT_TIMEOUT, allow_redirects=True)
    except requests.RequestException as exc:
        print(f"[!] Error en {url}: {exc}", file=sys.stderr)
        return None


def extract_links_from_html(html: str, base_url: str) -> tuple[set[str], set[str]]:
    soup = BeautifulSoup(html, "html.parser")
    links: set[str] = set()
    scripts: set[str] = set()

    for tag in soup.find_all("a", href=True):
        links.add(urljoin(base_url, tag["href"]))

    for tag in soup.find_all(["link", "form"]):
        ref = tag.get("href") or tag.get("action")
        if ref:
            links.add(urljoin(base_url, ref))

    for tag in soup.find_all("script", src=True):
        scripts.add(urljoin(base_url, tag["src"]))

    return links, scripts


def extract_endpoints_from_js(js_code: str) -> set[str]:
    found: set[str] = set()
    blocked_prefixes = ("data:", "blob:", "mailto:", "tel:")

    for pattern in JS_ENDPOINT_PATTERNS:
        for match in pattern.findall(js_code):
            if match and not match.startswith(blocked_prefixes):
                found.add(match)

    return found


def same_host(url: str, base: str) -> bool:
    try:
        return urlparse(url).netloc in ("", urlparse(base).netloc)
    except Exception:
        return False


def probe(session: requests.Session, url: str) -> tuple[dict, requests.Response | None]:
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
        response = session.get(url, timeout=DEFAULT_TIMEOUT, allow_redirects=True)
        record["status"] = response.status_code
        record["content_type"] = response.headers.get("Content-Type")
        record["length"] = len(response.content)
        record["headers"] = dict(response.headers)
        record["final_url"] = response.url
        return record, response
    except requests.RequestException as exc:
        record["error"] = str(exc)
        return record, None


def check_swagger(session: requests.Session, base: str) -> dict | None:
    candidates = ("/openapi.json", "/swagger.json", "/v2/api-docs", "/v3/api-docs")
    for path in candidates:
        url = urljoin(base, path)
        response = fetch(session, url)
        if response is None or response.status_code != 200:
            continue
        try:
            data = response.json()
            paths = list(data.get("paths", {}).keys())
            return {"source": url, "paths": paths}
        except ValueError:
            continue
    return None


def recon(
    base_url: str,
    max_depth: int = 1,
    max_urls: int = 200,
    delay: float = 0.2,
    max_js: int = 10,
) -> dict:
    session = create_session()
    report = {
        "target": base_url,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "config": {"max_depth": max_depth, "max_urls": max_urls, "delay": delay},
        "discovered_urls": [],
        "probed": [],
        "openapi": None,
    }

    queue: deque[tuple[str, int]] = deque([(base_url, 0)])
    for path in COMMON_PATHS:
        queue.append((urljoin(base_url, path), 0))

    openapi_info = check_swagger(session, base_url)
    if openapi_info:
        report["openapi"] = openapi_info
        for path in openapi_info["paths"]:
            queue.append((urljoin(base_url, path), 0))

    visited: set[str] = set()
    js_seen: set[str] = set()
    js_count = 0

    while queue and len(visited) < max_urls:
        url, depth = queue.popleft()

        if url in visited:
            continue
        if not same_host(url, base_url):
            continue
        if not url.startswith(("http://", "https://")):
            continue

        visited.add(url)

        if delay > 0:
            time.sleep(delay)

        record, response = probe(session, url)
        report["probed"].append(record)
        print(f"[{record.get('status', 'ERR')}] d={depth} {url}")

        if response is None or depth >= max_depth:
            continue

        content_type = (response.headers.get("Content-Type") or "").lower()
        if "html" not in content_type:
            continue

        links, scripts = extract_links_from_html(response.text, base_url)
        for link in links:
            if link not in visited and same_host(link, base_url):
                queue.append((link, depth + 1))

        for js_url in scripts:
            if js_count >= max_js:
                break
            if js_url in js_seen:
                continue

            js_seen.add(js_url)
            js_count += 1

            js_response = fetch(session, js_url)
            if js_response is None or js_response.status_code != 200:
                continue

            endpoints = extract_endpoints_from_js(js_response.text)
            for endpoint in endpoints:
                full_url = urljoin(base_url, endpoint)
                if full_url not in visited and same_host(full_url, base_url):
                    queue.append((full_url, depth + 1))

    report["discovered_urls"] = sorted(visited)
    return report


def render_html(report: dict) -> str:
    rows = []
    palette = {2: "#c8e6c9", 3: "#fff9c4", 4: "#ffccbc", 5: "#ef9a9a"}

    for row in report["probed"]:
        status = row.get("status") or "ERR"
        color = palette.get((row.get("status") or 0) // 100, "#eeeeee")
        rows.append(
            f"<tr style='background:{color}'>"
            f"<td>{row.get('url', '')}</td>"
            f"<td>{status}</td>"
            f"<td>{row.get('content_type', '') or ''}</td>"
            f"<td>{row.get('length', '') or ''}</td>"
            "</tr>"
        )

    openapi_block = ""
    if report.get("openapi"):
        items = "".join(f"<li>{path}</li>" for path in report["openapi"]["paths"])
        source = report["openapi"]["source"]
        openapi_block = f"<h2>OpenAPI ({source})</h2><ul>{items}</ul>"

    cfg = report.get("config", {})
    cfg_line = (
        f"<b>Profundidad:</b> {cfg.get('max_depth', '?')} · "
        f"<b>Máx URLs:</b> {cfg.get('max_urls', '?')} · "
        f"<b>Delay:</b> {cfg.get('delay', '?')}s"
    )

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
{openapi_block}
<h2>Resultados</h2>
<table><tr><th>URL</th><th>Status</th><th>Content-Type</th><th>Bytes</th></tr>
{''.join(rows)}
</table></body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Herramienta de reconocimiento (fase 1).")
    parser.add_argument("url", help="URL base, p.ej. https://ejemplo.com")
    parser.add_argument(
        "-o",
        "--output",
        default="recon_report",
        help="Prefijo de los archivos de salida (sin extensión).",
    )
    parser.add_argument(
        "--format",
        choices=["json", "html", "both"],
        default="both",
        help="Formato del informe.",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=1,
        help="Profundidad del crawler (0 = solo la raíz).",
    )
    parser.add_argument(
        "--max-urls",
        type=int,
        default=200,
        help="Tope máximo de URLs a visitar.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.2,
        help="Segundos de espera entre peticiones.",
    )
    parser.add_argument(
        "--max-js",
        type=int,
        default=10,
        help="Máximo de scripts JS a analizar.",
    )
    args = parser.parse_args()

    if not args.url.startswith(("http://", "https://")):
        parser.error("La URL debe empezar por http:// o https://")

    print(f"[*] Reconociendo {args.url} (depth={args.depth}, max_urls={args.max_urls})")
    report = recon(
        args.url,
        max_depth=args.depth,
        max_urls=args.max_urls,
        delay=args.delay,
        max_js=args.max_js,
    )
    print(f"[+] {len(report['discovered_urls'])} URLs visitadas")

    if args.format in ("json", "both"):
        json_path = f"{args.output}.json"
        with open(json_path, "w", encoding="utf-8") as file:
            json.dump(report, file, indent=2, ensure_ascii=False)
        print(f"[+] JSON -> {json_path}")

    if args.format in ("html", "both"):
        html_path = f"{args.output}.html"
        with open(html_path, "w", encoding="utf-8") as file:
            file.write(render_html(report))
        print(f"[+] HTML -> {html_path}")


if __name__ == "__main__":
    main()
