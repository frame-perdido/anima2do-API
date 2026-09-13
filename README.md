> ⚠️ Proyecto no oficial con fines educativos. No afiliado a Danimados. Esta API no aloja contenido, solo enlaza a fuentes públicas.

# Danimados API

API REST no oficial para consultar el catálogo público de Danimados.

## Endpoints

| Método | Endpoint | Descripción |
|---|---|---|
| GET | / | Health check |
| GET | /catalog | Catálogo de series |
| GET | /years | Lista de años |
| GET | /series/{id} | Detalles de una serie |
| GET | /seasons/{slug} | Temporadas de una serie |
| GET | /episodes?season_url= | Episodios de una temporada |
| GET | /servers?episode_url= | Servidores de un episodio |

## Ejemplos

GET /catalog?search=ranma
GET /catalog?year_id=3561
GET /years
GET /servers?episode_url=https://danimados.cc/episodios/ranma-%c2%bd-1x1/

## Respuesta de /servers

{
  "episode_id": "66943",
  "episode_url": "https://danimados.cc/episodios/ranma-%c2%bd-1x1/",
  "servidores": [
    {"nume": 1, "nombre": "VidHide", "dominio": "minochinos.com", "embed_url": "https://minochinos.com/embed/lx2eiwbp30ah"},
    {"nume": 2, "nombre": "StreamWish", "dominio": "hglink.to", "embed_url": "https://hglink.to/e/gyrg7kmhn0ij"}
  ]
}

## Tecnologías

FastAPI, httpx, Uvicorn

## Despliegue en Render

1. Sube este repositorio a GitHub
2. Crea un Web Service en render.com
3. Build Command: pip install -r requirements.txt
4. Start Command: uvicorn api:app --host 0.0.0.0 --port $PORT

## Local

pip install -r requirements.txt
uvicorn api:app --host 0.0.0.0 --port 8000

## Notas

Este proyecto no aloja contenido. Solo consulta datos públicos y devuelve enlaces a reproductores externos.

## Licencia

MIT
