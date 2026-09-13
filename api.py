from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response

import httpx
import re
import asyncio
import logging
import time

from typing import Optional
from urllib.parse import urlparse, urljoin

# ⚠️ CAMBIO CLAVE: patchright en lugar de playwright
from patchright.async_api import async_playwright
from playwright_stealth import stealth_async


# ============================================================
# LOGGING
# ============================================================

logger = logging.getLogger("uvicorn.error")


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="Danimados API",
    description="API para catálogo, servidores y detección HLS",
    version="2.3.0",
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# HEADERS
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
}


# ============================================================
# NOMBRES DE SERVIDORES
# ============================================================

NOMBRES = {
    "minochinos.com": "VidHide",
    "vidhidepro.com": "VidHide",
    "vidhide.com": "VidHide",
    "streamwish.to": "StreamWish",
    "hglink.to": "StreamWish",
    "wishfast.top": "StreamWish",
    "voe.sx": "Voe",
    "videoapp.zip": "VideoApp",
    "doodstream.com": "DoodStream",
    "dood.wf": "DoodStream",
    "filemoon.sx": "Filemoon",
    "filemoon.to": "Filemoon",
    "streamtape.com": "StreamTape",
    "mp4upload.com": "MP4Upload",
    "ok.ru": "OK.ru",
}


# ============================================================
# CONCURRENCIA
# ============================================================

BROWSER_LOCK = asyncio.Semaphore(1)


# ============================================================
# CACHÉ
# ============================================================

CACHE = {}
CACHE_TTL = 3600


# ============================================================
# STEALTH SCRIPT EXTRA
# (playwright-stealth ya hace mucho, pero añadimos lo nuestro)
# ============================================================

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
});

Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5]
});

Object.defineProperty(navigator, 'languages', {
    get: () => ['es-MX', 'es', 'en']
});

window.chrome = {
    runtime: {},
    loadTimes: function() {},
    csi: function() {},
    app: {}
};

const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);
"""


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def limpiar_dominio(url: str) -> str:
    try:
        dominio = urlparse(url).netloc.lower()
        if dominio.startswith("www."):
            dominio = dominio[4:]
        return dominio
    except Exception:
        return ""


def es_hls(url: str) -> bool:
    lower = url.lower()
    return ".m3u8" in lower or "m3u8" in lower


def construir_headers_proxy(referer: str = "") -> dict:
    headers = {**HEADERS}
    if referer:
        headers["Referer"] = referer
        try:
            parsed = urlparse(referer)
            headers["Origin"] = f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            pass
    return headers


# ============================================================
# ROOT
# ============================================================

@app.get("/")
async def read_root():
    return {
        "message": "Danimados API está funcionando",
        "version": "2.3.0",
        "playwright": "patchright",
        "stealth": True,
        "hls_resolver": True,
        "proxy": True,
    }


# ============================================================
# CATALOGO
# ============================================================

@app.get("/catalog")
async def get_catalog(
    search: Optional[str] = None,
    year_id: Optional[int] = None,
    page: int = 1,
    per_page: int = 20,
):

    params = {"per_page": per_page, "page": page}
    if search:
        params["search"] = search
    if year_id:
        params["dtyear"] = year_id

    try:
        async with httpx.AsyncClient(
            headers=HEADERS, timeout=20, follow_redirects=True
        ) as client:
            response = await client.get(
                "https://danimados.cc/wp-json/wp/v2/tvshows",
                params=params,
            )
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Error al obtener el catálogo",
                )
            return {
                "total": response.headers.get("x-wp-total"),
                "total_pages": response.headers.get("x-wp-totalpages"),
                "page": page,
                "results": response.json(),
            }
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Error conectando con Danimados: {str(e)}",
        )


# ============================================================
# AÑOS
# ============================================================

@app.get("/years")
async def get_years():
    try:
        async with httpx.AsyncClient(
            headers=HEADERS, timeout=20, follow_redirects=True
        ) as client:
            response = await client.get(
                "https://danimados.cc/wp-json/wp/v2/dtyear",
                params={"per_page": 100},
            )
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Error al obtener los años",
                )
            return [
                {"id": year["id"], "year": year["name"]}
                for year in response.json()
            ]
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Error conectando con Danimados: {str(e)}",
        )


# ============================================================
# SERIE
# ============================================================

@app.get("/series/{serie_id}")
async def get_serie(serie_id: int):
    try:
        async with httpx.AsyncClient(
            headers=HEADERS, timeout=20, follow_redirects=True
        ) as client:
            response = await client.get(
                f"https://danimados.cc/wp-json/wp/v2/tvshows/{serie_id}"
            )
            if response.status_code != 200:
                raise HTTPException(
                    status_code=404, detail="Serie no encontrada"
                )
            return response.json()
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Error conectando con Danimados: {str(e)}",
        )


# ============================================================
# TEMPORADAS
# ============================================================

@app.get("/seasons/{serie_slug}")
async def get_seasons(serie_slug: str):
    try:
        async with httpx.AsyncClient(
            headers=HEADERS, timeout=20, follow_redirects=True
        ) as client:
            response = await client.get(
                "https://danimados.cc/wp-json/wp/v2/seasons",
                params={"search": serie_slug, "per_page": 50},
            )
            if response.status_code != 200:
                raise HTTPException(
                    status_code=404, detail="Temporadas no encontradas"
                )
            return response.json()
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Error conectando con Danimados: {str(e)}",
        )


# ============================================================
# EPISODIOS
# ============================================================

@app.get("/episodes")
async def get_episodes(season_url: str):
    try:
        async with httpx.AsyncClient(
            headers=HEADERS, timeout=20, follow_redirects=True
        ) as client:
            response = await client.get(season_url)
            if response.status_code != 200:
                raise HTTPException(
                    status_code=404, detail="Temporada no encontrada"
                )
            enlaces = re.findall(
                r'href=["\']([^"\']+)["\']', response.text
            )
            enlaces = list(dict.fromkeys(enlaces))
            return {"season_url": season_url, "episodes": enlaces}
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Error obteniendo episodios: {str(e)}",
        )


# ============================================================
# SERVIDORES
# ============================================================

@app.get("/servers")
async def get_servers(episode_url: str):
    try:
        async with httpx.AsyncClient(
            headers=HEADERS, timeout=20, follow_redirects=True
        ) as client:
            response = await client.get(episode_url)
            if response.status_code != 200:
                raise HTTPException(
                    status_code=404,
                    detail="No se pudo abrir el episodio",
                )
            match_id = re.search(
                r'data-post=["\'](\d+)["\']', response.text
            )
            if not match_id:
                raise HTTPException(
                    status_code=404,
                    detail="No se encontró el ID del episodio",
                )
            episode_id = match_id.group(1)
            servidores = []
            for nume in range(1, 6):
                try:
                    ajax_response = await client.post(
                        "https://danimados.cc/wp-admin/admin-ajax.php",
                        data={
                            "action": "doo_player_ajax",
                            "post": episode_id,
                            "nume": str(nume),
                            "type": "tv",
                        },
                        headers={
                            **HEADERS,
                            "X-Requested-With": "XMLHttpRequest",
                            "Referer": episode_url,
                            "Origin": "https://danimados.cc",
                        },
                    )
                    if ajax_response.status_code != 200:
                        continue
                    data = ajax_response.json()
                    embed_url = data.get("embed_url", "")
                    if not embed_url:
                        continue
                    dominio = limpiar_dominio(embed_url)
                    servidores.append(
                        {
                            "nume": nume,
                            "nombre": NOMBRES.get(dominio, dominio),
                            "dominio": dominio,
                            "embed_url": embed_url,
                        }
                    )
                except Exception:
                    continue
            return {
                "episode_id": episode_id,
                "episode_url": episode_url,
                "servidores": servidores,
            }
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Error obteniendo servidores: {str(e)}",
        )


# ============================================================
# RESOLVER HLS
# ============================================================

@app.get("/resolve")
async def resolve_player(embed_url: str, wait: int = 20):

    if not embed_url.startswith(("http://", "https://")):
        raise HTTPException(400, "embed_url no es una URL válida")

    ahora = time.time()
    if embed_url in CACHE:
        ts, data = CACHE[embed_url]
        if ahora - ts < CACHE_TTL:
            logger.info(f"[resolve] Cache hit: {embed_url}")
            return {**data, "cached": True}

    wait = max(5, min(wait, 35))

    hls_urls = []
    mp4_urls = []

    logger.info(f"[resolve] Iniciando: {embed_url}")

    async with BROWSER_LOCK:

        async with async_playwright() as playwright:

            browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--window-size=1280,720",
                ],
            )

            context = await browser.new_context(
                user_agent=HEADERS["User-Agent"],
                viewport={"width": 1280, "height": 720},
                locale="es-MX",
                timezone_id="America/Mexico_City",
            )

            await context.add_init_script(STEALTH_SCRIPT)

            page = await context.new_page()

            # ⚠️ APLICAR STEALTH
            await stealth_async(page)

            async def bloquear(route):
                tipo = route.request.resource_type
                if tipo in ("image", "font", "stylesheet"):
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/*", bloquear)

            def registrar_request(request):
                url = request.url
                lower = url.lower()
                if ".m3u8" in lower or "m3u8" in lower:
                    if url not in hls_urls:
                        hls_urls.append(url)
                if ".mp4" in lower and "video" not in lower:
                    if url not in mp4_urls:
                        mp4_urls.append(url)

            def registrar_response(response):
                url = response.url
                lower = url.lower()
                if ".m3u8" in lower or "m3u8" in lower:
                    if url not in hls_urls:
                        hls_urls.append(url)

            page.on("request", registrar_request)
            page.on("response", registrar_response)

            try:
                await page.goto(
                    embed_url,
                    wait_until="domcontentloaded",
                    timeout=30000,
                )

                # Espera activa
                elapsed = 0
                step = 2
                while elapsed < wait and not hls_urls:
                    await asyncio.sleep(step)
                    elapsed += step

                if hls_urls:
                    await asyncio.sleep(3)

            except Exception as e:
                logger.error(f"[resolve] Error: {e}")
                raise HTTPException(
                    502, f"Error abriendo el reproductor: {str(e)}"
                )

            finally:
                await browser.close()

    hls_urls = list(dict.fromkeys(hls_urls))
    mp4_urls = list(dict.fromkeys(mp4_urls))

    best = hls_urls[0] if hls_urls else (mp4_urls[0] if mp4_urls else None)

    resultado = {
        "embed_url": embed_url,
        "hls_found": len(hls_urls),
        "hls": hls_urls,
        "mp4": mp4_urls,
        "best": best,
    }

    logger.info(
        f"[resolve] Resultado: hls={len(hls_urls)} mp4={len(mp4_urls)} best={best}"
    )

    CACHE[embed_url] = (ahora, resultado)

    return resultado


# ============================================================
# RESOLVER HLS DEBUG
# ============================================================

@app.get("/resolve/debug")
async def resolve_player_debug(embed_url: str, wait: int = 20):

    if not embed_url.startswith(("http://", "https://")):
        raise HTTPException(400, "embed_url no es válido")

    wait = max(5, min(wait, 35))

    hls_urls = []
    video_urls = []
    todas_las_urls = []

    async with BROWSER_LOCK:

        async with async_playwright() as playwright:

            browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled",
                ],
            )

            context = await browser.new_context(
                user_agent=HEADERS["User-Agent"],
                viewport={"width": 1280, "height": 720},
                locale="es-MX",
            )

            await context.add_init_script(STEALTH_SCRIPT)

            page = await context.new_page()
            await stealth_async(page)

            def registrar_request(request):
                url = request.url
                todas_las_urls.append(url)
                lower = url.lower()
                if ".m3u8" in lower or "m3u8" in lower:
                    if url not in hls_urls:
                        hls_urls.append(url)
                if any(x in lower for x in (".mp4", ".m3u8", ".ts", ".m4s", "videoplayback")):
                    if url not in video_urls:
                        video_urls.append(url)

            page.on("request", registrar_request)

            try:
                await page.goto(
                    embed_url,
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                await asyncio.sleep(wait)
            except Exception as e:
                raise HTTPException(
                    502, f"Error abriendo reproductor: {str(e)}"
                )
            finally:
                await browser.close()

    return {
        "embed_url": embed_url,
        "hls": list(dict.fromkeys(hls_urls)),
        "video": list(dict.fromkeys(video_urls)),
        "requests_checked": len(todas_las_urls),
        "all_requests": todas_las_urls,
    }


# ============================================================
# PROXY BINARIO
# ============================================================

@app.get("/proxy")
async def proxy_video(url: str, referer: str = ""):

    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "URL inválida")

    headers = construir_headers_proxy(referer)

    try:
        client = httpx.AsyncClient(
            timeout=60, follow_redirects=True, http2=True
        )

        req = client.build_request("GET", url, headers=headers)
        resp = await client.send(req, stream=True)

        if resp.status_code >= 400:
            await resp.aclose()
            await client.aclose()
            raise HTTPException(
                resp.status_code, "Error del servidor origen"
            )

        async def stream():
            try:
                async for chunk in resp.aiter_raw():
                    yield chunk
            finally:
                await resp.aclose()
                await client.aclose()

        content_type = resp.headers.get(
            "content-type", "application/octet-stream"
        )

        return StreamingResponse(
            stream(),
            media_type=content_type,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-cache",
            },
        )

    except httpx.RequestError as e:
        raise HTTPException(502, f"Error proxeando: {str(e)}")


# ============================================================
# PROXY M3U8 CON REESCRITURA
# ============================================================

def reescribir_m3u8(contenido: str, base_url: str, referer: str) -> str:

    lineas_salida = []

    for linea in contenido.splitlines():

        stripped = linea.strip()

        if not stripped or stripped.startswith("#"):
            lineas_salida.append(linea)
            continue

        url_abs = urljoin(base_url, stripped)
        lower = url_abs.lower()

        ref_enc = referer if referer else ""

        if ".m3u8" in lower:
            proxied = (
                f"/proxy_m3u8?url={url_abs}&referer={ref_enc}"
            )
        else:
            proxied = (
                f"/proxy?url={url_abs}&referer={ref_enc}"
            )

        lineas_salida.append(proxied)

    return "\n".join(lineas_salida)


@app.get("/proxy_m3u8")
async def proxy_m3u8(url: str, referer: str = ""):

    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "URL inválida")

    headers = construir_headers_proxy(referer)

    try:
        async with httpx.AsyncClient(
            timeout=30, follow_redirects=True, http2=True
        ) as client:
            response = await client.get(url, headers=headers)

            if response.status_code >= 400:
                raise HTTPException(
                    response.status_code,
                    f"Origen devolvió {response.status_code}",
                )

            contenido = response.text

            if "#EXTM3U" not in contenido:
                return Response(
                    content=contenido,
                    media_type="application/vnd.apple.mpegurl",
                    headers={"Access-Control-Allow-Origin": "*"},
                )

            base_url = str(response.url)
            reescrito = reescribir_m3u8(contenido, base_url, referer)

            return Response(
                content=reescrito,
                media_type="application/vnd.apple.mpegurl",
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Cache-Control": "no-cache",
                },
            )

    except httpx.RequestError as e:
        raise HTTPException(502, f"Error proxeando m3u8: {str(e)}")


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "danimados-api",
        "version": "2.3.0",
    }


@app.get("/health/playwright")
async def health_playwright():
    try:
        async with BROWSER_LOCK:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
                version = browser.version
                await browser.close()
                return {
                    "status": "ok",
                    "engine": "patchright",
                    "chromium": version,
                }
    except Exception as e:
        logger.error(f"[health/playwright] {e}")
        raise HTTPException(500, f"Chromium no arranca: {str(e)}")
