from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from routers.projects import router as projects_router
from utils.errors import register_exception_handlers
from utils.rate_limit import limiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    from bootstrap import run_bootstrap
    run_bootstrap()
    yield

app = FastAPI(
    title="Glenigan Projects API",
    version="2.0.0",
    description="Returns construction projects filtered by area, project name, and company.",
    lifespan=lifespan,
)

app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": {"error": "rate_limit_exceeded", "message": str(exc.detail)}},
    )

app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

# Register central error handlers
register_exception_handlers(app)

# Include routers with API versioning
app.include_router(projects_router, prefix="/api/v1")

@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}
