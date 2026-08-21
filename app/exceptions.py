"""
exceptions.py

Exception handlers registered on the FastAPI app. The guiding rule:
the client always gets a safe, generic message plus a request_id they
can hand to support; the *server-side log* always gets the full
exception with a stack trace, correlated to that same request_id via
the logging context bound in middleware.py. Never make someone choose
between "helpful error for the client" and "no internal details
leaked" - log the detail, return the summary.
"""

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from logging_config import get_logger

log = get_logger(__name__)


def register_exception_handlers(app) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        log.info("http_exception", status_code=exc.status_code, detail=exc.detail)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = jsonable_encoder(exc.errors())
        log.info("validation_error", errors=errors)
        return JSONResponse(
            status_code=422,
            content={"detail": "Invalid request", "errors": errors},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # Never leak internals (e.g. connection strings) in error responses -
        # small detail, but exactly what an AZ-500-minded reviewer checks for.
        log.error("unhandled_exception", exc_info=True)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})