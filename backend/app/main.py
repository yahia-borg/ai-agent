# Load .env file before anything else
from dotenv import load_dotenv
load_dotenv()

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

from contextlib import asynccontextmanager
from app.services.qdrant_service import get_qdrant_service
from app.core.langsmith_config import get_langsmith_callbacks
from app.core.environment import validate_on_startup

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Validate environment variables on startup
    logger = logging.getLogger(__name__)
    try:
        validate_on_startup()
    except ValueError as e:
        logger.error(f"Startup validation failed: {e}")
        raise
    
    # Load embedding model on startup
    logger.info("Loading embedding model on startup...")
    get_qdrant_service()
    
    # Initialize LangSmith tracing (sets environment variables)
    get_langsmith_callbacks()
    
    yield
    # Clean up resources if needed (e.g. close DB connections)

app = FastAPI(
    title="AI Construction Agent API",
    description="API for AI-powered construction quotation generation",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Store environment in app state
app.state.ENVIRONMENT = settings.ENVIRONMENT

# Debug middleware to log OPTIONS requests (add this first so it runs last)
@app.middleware("http")
async def debug_options_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        debug_logger = logging.getLogger("cors_debug")
        debug_logger.info(f"=== OPTIONS DEBUG ===")
        debug_logger.info(f"Path: {request.url.path}")
        debug_logger.info(f"Headers: {dict(request.headers)}")
        debug_logger.info(f"=== END DEBUG ===")
    response = await call_next(request)
    if request.method == "OPTIONS":
        debug_logger = logging.getLogger("cors_debug")
        debug_logger.info(f"Response status: {response.status_code}")
    return response

# CORS middleware - MUST be added first (runs last in middleware chain)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Add exception handler middleware after CORS
app.middleware("http")(exception_handler)

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

