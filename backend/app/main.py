from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.core.config import settings
from app.api.v1.api import api_router
from app.core.middleware import exception_handler
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI(
    title="AI Construction Agent API",
    description="API for AI-powered construction quotation generation",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Store environment in app state
app.state.ENVIRONMENT = settings.ENVIRONMENT

# Add exception handler middleware
app.middleware("http")(exception_handler)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add validation error handler for better debugging
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger = logging.getLogger(__name__)
    logger.error(f"Validation error on {request.url.path}: {exc.errors()}")
    try:
        body = await request.body()
        logger.error(f"Request body: {body.decode('utf-8')[:500]}")  # Log first 500 chars
    except Exception as e:
        logger.error(f"Could not read request body: {e}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()}
    )

# Include API router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/")
async def root():
    return {"message": "AI Construction Agent API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}

