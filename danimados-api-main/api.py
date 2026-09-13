from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import httpx
import re
import asyncio

from typing import Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="Danimados API",
    description="API para catálogo, servidores y detección HLS",
    version="2.1.0",
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
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-MX,es;q=0.9",
}


# ============================================================
# NOMBRES DE SERVIDORES
# ============================================================

NOMBRES = {
    "minochinos.com": "VidHide",
    "vidhidepro.com": "VidHide",
    "streamwish.to": "StreamWish",
    "hglink.to": "StreamWish",
    "voe.sx": "Voe",
    "videoapp.zip": "VideoApp",
    "doodstream.com": "DoodStream",
}


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def limpiar_dominio(url: str) -> str:
    """
    Obtiene el dominio limpio de una URL.
    """

    try:
        dominio = urlparse(url).netloc.lower()

        if dominio.startswith("www."):
            dominio = dominio[4:]

        return dominio

    except Exception:
        return ""


def es_hls(url: str) -> bool:
    """
    Comprueba si una URL parece ser un manifiesto HLS.
    """

    lower = url.lower()

    return (
        ".m3u8" in lower
        or "m3u8" in lower
    )


# ============================================================
# ROOT
# ============================================================

@app.get("/")
async def read_root():

    return {
        "message": "Danimados API está funcionando",
        "version": "2.1.0",
        "playwright": True,
        "hls_resolver": True,
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

    params = {
        "per_page": per_page,
        "page": page,
    }

    if search:
        params["search"] = search

    if year_id:
        params["dtyear"] = year_id

    try:

        async with httpx.AsyncClient(
            headers=HEADERS,
            timeout=20,
            follow_redirects=True,
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
                "total_pages": response.headers.get(
                    "x-wp-totalpages"
                ),
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
            headers=HEADERS,
            timeout=20,
            follow_redirects=True,
        ) as client:

            response = await client.get(
                "https://danimados.cc/wp-json/wp/v2/dtyear",
                params={
                    "per_page": 100
                },
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Error al obtener los años",
                )

            return [
                {
                    "id": year["id"],
                    "year": year["name"],
                }
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
            headers=HEADERS,
            timeout=20,
            follow_redirects=True,
        ) as client:

            response = await client.get(
                f"https://danimados.cc/wp-json/wp/v2/tvshows/{serie_id}"
            )

            if response.status_code != 200:

                raise HTTPException(
                    status_code=404,
                    detail="Serie no encontrada",
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
            headers=HEADERS,
            timeout=20,
            follow_redirects=True,
        ) as client:

            response = await client.get(
                "https://danimados.cc/wp-json/wp/v2/seasons",
                params={
                    "search": serie_slug,
                    "per_page": 50,
                },
            )

            if response.status_code != 200:

                raise HTTPException(
                    status_code=404,
                    detail="Temporadas no encontradas",
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
            headers=HEADERS,
            timeout=20,
            follow_redirects=True,
        ) as client:

            response = await client.get(season_url)

            if response.status_code != 200:

                raise HTTPException(
                    status_code=404,
                    detail="Temporada no encontrada",
                )

            enlaces = re.findall(
                r'href=["\']([^"\']+)["\']',
                response.text,
            )

            enlaces = list(
                dict.fromkeys(enlaces)
            )

            return {
                "season_url": season_url,
                "episodes": enlaces,
            }

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
            headers=HEADERS,
            timeout=20,
            follow_redirects=True,
        ) as client:

            response = await client.get(
                episode_url
            )

            if response.status_code != 200:

                raise HTTPException(
                    status_code=404,
                    detail="No se pudo abrir el episodio",
                )

            match_id = re.search(
                r'data-post=["\'](\d+)["\']',
                response.text,
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
                        },
                    )

                    if ajax_response.status_code != 200:
                        continue

                    data = ajax_response.json()

                    embed_url = data.get(
                        "embed_url",
                        ""
                    )

                    if not embed_url:
                        continue

                    dominio = limpiar_dominio(
                        embed_url
                    )

                    servidores.append(
                        {
                            "nume": nume,
                            "nombre": NOMBRES.get(
                                dominio,
                                dominio,
                            ),
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
async def resolve_player(
    embed_url: str,
    wait: int = 12,
):

    if not embed_url.startswith(
        ("http://", "https://")
    ):

        raise HTTPException(
            status_code=400,
            detail="embed_url no es una URL válida",
        )

    wait = max(
        3,
        min(wait, 30)
    )

    hls_urls = []

    async with async_playwright() as playwright:

        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )

        context = await browser.new_context(
            user_agent=HEADERS["User-Agent"],
            viewport={
                "width": 1280,
                "height": 720,
            },
            locale="es-MX",
        )

        page = await context.new_page()

        def registrar_request(request):

            url = request.url

            if es_hls(url):

                if url not in hls_urls:
                    hls_urls.append(url)

        page.on(
            "request",
            registrar_request
        )

        try:

            await page.goto(
                embed_url,
                wait_until="domcontentloaded",
                timeout=30000,
            )

            await asyncio.sleep(wait)

        except Exception as e:

            raise HTTPException(
                status_code=502,
                detail=f"Error abriendo el reproductor: {str(e)}",
            )

        finally:

            await browser.close()

    hls_urls = list(
        dict.fromkeys(hls_urls)
    )

    return {
        "embed_url": embed_url,
        "hls_found": len(hls_urls),
        "hls": hls_urls,
    }


# ============================================================
# RESOLVER HLS DEBUG
# ============================================================

@app.get("/resolve/debug")
async def resolve_player_debug(
    embed_url: str,
    wait: int = 12,
):

    if not embed_url.startswith(
        ("http://", "https://")
    ):

        raise HTTPException(
            status_code=400,
            detail="embed_url no es válido",
        )

    wait = max(
        3,
        min(wait, 30)
    )

    hls_urls = []
    video_urls = []
    todas_las_urls = []

    async with async_playwright() as playwright:

        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )

        context = await browser.new_context(
            user_agent=HEADERS["User-Agent"],
            viewport={
                "width": 1280,
                "height": 720,
            },
            locale="es-MX",
        )

        page = await context.new_page()

        def registrar_request(request):

            url = request.url

            todas_las_urls.append(url)

            lower = url.lower()

            if (
                ".m3u8" in lower
                or "m3u8" in lower
            ):

                if url not in hls_urls:
                    hls_urls.append(url)

            if (
                ".mp4" in lower
                or ".m3u8" in lower
                or ".ts" in lower
                or ".m4s" in lower
                or "videoplayback" in lower
            ):

                if url not in video_urls:
                    video_urls.append(url)

        page.on(
            "request",
            registrar_request
        )

        try:

            await page.goto(
                embed_url,
                wait_until="domcontentloaded",
                timeout=30000,
            )

            await asyncio.sleep(wait)

        except Exception as e:

            raise HTTPException(
                status_code=502,
                detail=f"Error abriendo reproductor: {str(e)}",
            )

        finally:

            await browser.close()

    return {
        "embed_url": embed_url,
        "hls": list(
            dict.fromkeys(hls_urls)
        ),
        "video": list(
            dict.fromkeys(video_urls)
        ),
        "requests_checked": len(
            todas_las_urls
        ),
        "all_requests": todas_las_urls,
    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
async def health():

    return {
        "status": "ok",
        "service": "danimados-api",
        "version": "2.1.0",
    }
