"""FastAPI application: wiring, HTTP concerns and error handling only.

Two endpoints keep the slow, optional AI step away from the fast, deterministic one:
``POST /api/plan`` never waits on a model, and ``POST /api/ideas`` adds personalised ideas.
"""

from __future__ import annotations

import math
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .ai import GeminiTextGenerator, NullTextGenerator, TextGenerationPort
from .config import Settings
from .models import IdeasResponse, Plan, PlanRequest
from .planner import build_plan
from .security import SECURITY_HEADERS, SlidingWindowRateLimiter, client_ip
from .services import IdeaService

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def create_app(
    settings: Settings | None = None, generator: TextGenerationPort | None = None
) -> FastAPI:
    """Builds the application.

    Args:
        settings: Configuration; read from the environment when omitted.
        generator: Text-generation port; Gemini when a key is configured, otherwise a null
            generator. Tests pass a fake here.

    Returns:
        A configured FastAPI app.
    """
    settings = settings or Settings.from_env()
    if generator is None:
        generator = (
            GeminiTextGenerator(
                settings.gemini_api_key,
                settings.gemini_model,
                settings.gemini_timeout_s,
                settings.max_concurrent_ai,
            )
            if settings.gemini_api_key
            else NullTextGenerator()
        )
    ideas_service = IdeaService(generator)
    limiter = SlidingWindowRateLimiter(settings.rate_limit_requests, settings.rate_limit_window_s)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await generator.aclose()

    # Interactive docs load third-party scripts, which our CSP forbids; keep the surface small.
    app = FastAPI(
        title="Celebration & Event Planner",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    @app.middleware("http")
    async def harden(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        declared = request.headers.get("content-length", "0")
        if declared.isdigit() and int(declared) > settings.max_body_bytes:
            response: Response = JSONResponse({"error": "Request body too large."}, status_code=413)
        else:
            response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]}
            for e in exc.errors()
        ]
        return JSONResponse({"errors": errors}, status_code=422)

    def rate_limit(request: Request) -> None:
        client = client_ip(
            request.headers.get("x-forwarded-for"),
            request.client.host if request.client else None,
            settings.trusted_proxy_hops,
        )
        retry_after = limiter.check(client)
        if retry_after:
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please wait a moment and try again.",
                headers={"Retry-After": str(math.ceil(retry_after))},
            )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/plan", response_model=Plan, dependencies=[Depends(rate_limit)])
    async def create_plan(req: PlanRequest) -> Plan:
        return build_plan(req, today=date.today())

    @app.post("/api/ideas", response_model=IdeasResponse, dependencies=[Depends(rate_limit)])
    async def create_ideas(req: PlanRequest) -> IdeasResponse:
        days_until = (req.event_date - date.today()).days
        return await ideas_service.suggest(req, days_until)

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
