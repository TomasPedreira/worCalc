"""FastAPI application for the browser-based worCalc workflow."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..domain.calibration import Point
from ..paths import BALLISTICS_CSV, MAPS_DIR
from .service import FireMissionCalculator, MapNotFoundError


STATIC_DIR = Path(__file__).resolve().parent / "static"
NO_STORE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
}
MAP_CACHE_HEADERS = NO_STORE_HEADERS
WEB_ASSET_CACHE_HEADERS = NO_STORE_HEADERS


class PointRequest(BaseModel):
    x: float
    y: float


class SolutionRequest(BaseModel):
    map_id: str
    gun: PointRequest
    target: PointRequest
    cannon: str
    projectile: str
    method: str


def create_app(
    maps_dir: Path = MAPS_DIR,
    ballistics_csv: Path = BALLISTICS_CSV,
    paks_root: Path | None = None,
) -> FastAPI:
    calculator = FireMissionCalculator(maps_dir, ballistics_csv, paks_root)
    app = FastAPI(title="worCalc", version="0.1.0")
    app.state.calculator = calculator
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.middleware("http")
    async def prevent_stale_web_ui(request: Request, call_next):
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            response.headers.update(WEB_ASSET_CACHE_HEADERS)
        return response

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(
            STATIC_DIR / "index.html",
            headers=WEB_ASSET_CACHE_HEADERS,
        )

    @app.get("/api/options")
    def options() -> dict[str, object]:
        return {
            "weapons": calculator.weapons,
            "physics": calculator.physics_profiles,
            "methods": calculator.methods,
            "defaults": {
                "cannon": "3-inch Ordnance",
                "projectile": "Shell",
                "method": calculator.default_method,
            },
        }

    @app.get("/api/maps")
    def maps() -> list[dict[str, object]]:
        return [
            {
                **asdict(info),
                "image_url": (
                    f"/api/maps/{info.identifier}/image?style=parchment&format=webp"
                ),
                "thumbnail_url": f"/api/maps/{info.identifier}/thumbnail",
            }
            for info in calculator.list_maps()
        ]

    @app.get("/api/maps/{map_id}/image")
    def map_image(
        map_id: str,
        style: str = "parchment",
        format: str = "png",
    ) -> Response:
        try:
            path = calculator.image_path(map_id)
        except MapNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        if style == "raw":
            return FileResponse(
                path,
                media_type="image/png",
                headers=MAP_CACHE_HEADERS,
            )
        if style != "parchment":
            raise HTTPException(status_code=400, detail=f"Unknown map style: {style}")
        if format == "webp":
            return Response(
                content=calculator.parchment_webp_image_bytes(map_id),
                media_type="image/webp",
                headers=MAP_CACHE_HEADERS,
            )
        if format != "png":
            raise HTTPException(
                status_code=400,
                detail=f"Unknown map image format: {format}",
            )
        return Response(
            content=calculator.parchment_image_bytes(map_id),
            media_type="image/png",
            headers=MAP_CACHE_HEADERS,
        )

    @app.get("/api/maps/{map_id}/thumbnail")
    def map_thumbnail(map_id: str) -> Response:
        try:
            content = calculator.parchment_thumbnail_bytes(map_id)
        except MapNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return Response(
            content=content,
            media_type="image/webp",
            headers=MAP_CACHE_HEADERS,
        )

    @app.get("/api/maps/{map_id}/locations")
    def map_locations(map_id: str) -> list[dict[str, object]]:
        try:
            return [
                asdict(location)
                for location in calculator.map_locations(map_id)
            ]
        except MapNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/solutions")
    def solution(request: SolutionRequest) -> dict[str, object]:
        try:
            result = calculator.calculate(
                request.map_id,
                Point(request.gun.x, request.gun.y),
                Point(request.target.x, request.target.y),
                request.cannon,
                request.projectile,
                request.method,
            )
        except MapNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return asdict(result)

    return app


app = create_app()
