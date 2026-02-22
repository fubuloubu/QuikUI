from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment, TemplateNotFound
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

# Global template environment for error rendering
_error_template_env: Environment | None = None


class ErrorDetail(BaseModel):
    """A single validation error detail item."""

    loc: list[str | int] = Field(default_factory=list)
    msg: str
    type: str


def _get_status_text(status_code: int) -> str:
    """Get human-readable status text for common HTTP status codes."""
    status_map = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        406: "Not Acceptable",
        409: "Conflict",
        422: "Validation Error",
    }
    return status_map.get(status_code, "Error")


def _is_html_request(request: Request) -> bool:
    """
    Check if the request expects an HTML response using the same heuristic
    as QuikUI's request_if_html_response_needed dependency.
    """
    # Check for HTMX request
    if request.headers.get("hx-request"):
        return True

    # Check for QuikUI variant header
    if request.headers.get("qk-variant"):
        return True

    # Check Content-Type
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json") or content_type.startswith("application/jsonl"):
        return False

    # Check Accept header
    accept = request.headers.get("accept", "")
    if accept == "text/event-stream":
        return True
    if "text/html" in accept:
        return True

    return False


def _get_default_template_env() -> Environment:
    from jinja2 import PackageLoader

    return Environment(
        loader=PackageLoader("quikui", "templates"),
        autoescape=True,
    )


def _render_exception_template(exc: Exception, context: dict) -> str | None:
    """Render exception if a template exists, or None if no template found."""

    template_name = f"{exc.__class__.__name__}.html"

    # Try user's custom template environment first
    if env := _error_template_env:
        try:
            template = env.get_template(template_name)
        except TemplateNotFound:
            # Not found, so check for match with our built-in exception templates
            pass

        else:
            return template.render(**context)

    env = _get_default_template_env()
    try:
        template = env.get_template(template_name)
    except TemplateNotFound:
        # We don't have a template, so fall back to QuikUI's built-in HTML
        return None

    return template.render(**context)


def _create_htmx_error_response(
    html_content: str,
    status_code: int,
    retarget: str | None = None,
    reswap: str | None = None,
) -> HTMLResponse:
    """Create an HTML error response with optional HTMX headers"""

    headers = {}

    # Add HTMX retargeting headers if specified
    if retarget:
        headers["HX-Retarget"] = retarget
    if reswap:
        headers["HX-Reswap"] = reswap

    return HTMLResponse(
        content=html_content,
        status_code=status_code,
        headers=headers,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
    """
    Handle HTTPException for both HTML and JSON requests.

    For HTML/HTMX requests:
    - If exception is TemplatedHTTPException, uses its custom template and HTMX config
    - Otherwise, tries to find a template named {ExceptionClassName}.html
    - Falls back to built-in HTTPException.html template
    - If no template found, returns FastAPI's default JSON response

    For JSON requests:
    - Returns standard FastAPI JSON error response
    """
    from .exceptions import TemplatedHTTPException

    # NOTE: Only render 4xx exceptions, leave 5xx alone
    if (400 <= exc.status_code < 500) and _is_html_request(request):
        if isinstance(exc, TemplatedHTTPException):
            # Get error targeting configuration from exception
            error_container = exc.error_container
            error_swap = exc.error_swap
            variant = exc.template_variant

            # Use the exception's own template rendering
            return _create_htmx_error_response(
                html_content=exc.model_dump_html(template_variant=variant),
                status_code=exc.status_code,
                retarget=error_container,
                reswap=error_swap,
            )

        # Try to render using template lookup by exception class name
        context = {
            "exception": exc,
            "status_code": exc.status_code,
            "status_text": _get_status_text(exc.status_code),
            "detail": exc.detail,
        }

        if html_content := _render_exception_template(exc, context):
            return _create_htmx_error_response(
                html_content=html_content,
                status_code=exc.status_code,
            )

        # Fall back to default behavior to mimic FastAPI's default handling

    # Standard JSON response for API clients
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> Response:
    """
    Handle Pydantic RequestValidationError (422 errors) for both HTML and JSON requests.

    For HTML/HTMX requests:
    - Tries to find a template named RequestValidationError.html or ValidationError.html
    - Template receives a list of ErrorDetail objects
    - Falls back to FastAPI's default JSON response if no template found

    For JSON requests:
    - Returns standard FastAPI validation error response with full details
    """
    if _is_html_request(request):
        error_details = [
            ErrorDetail(
                loc=list(err.get("loc", [])),
                msg=err.get("msg", "Validation error"),
                type=err.get("type", "value_error"),
            )
            for err in exc.errors()
        ]

        # Try to render using template
        context = {
            "exception": exc,
            "errors": error_details,
            "status_code": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "status_text": _get_status_text(status.HTTP_422_UNPROCESSABLE_CONTENT),
        }

        if html_content := _render_exception_template(exc, context):
            # For validation errors, target the nearest error container by default
            # Wrap in error-styled container div
            return _create_htmx_error_response(
                html_content=html_content,
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                retarget="closest .quikui-error-container",
                reswap="outerHTML",
            )

    # Standard JSON response with full validation details
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": exc.errors()},
    )


def setup_error_handlers(
    app: FastAPI,
    template_env: Environment | None = None,
) -> None:
    """
    Register HTMX-friendly error handlers for a FastAPI application.

    This function registers exception handlers that automatically detect HTML vs JSON
    requests and return appropriate error responses:
    - HTML/HTMX: Rendered templates with optional HTMX retargeting headers
    - JSON: Standard FastAPI JSON error responses

    Template Lookup Strategy (in priority order):
    1. TemplatedHTTPException → Uses its own model_dump_html() with custom HTMX config
    2. HTTPException → Tries {ExceptionClassName}.html (e.g., HTTPException.html)
    3. RequestValidationError → Tries RequestValidationError.html
    4. Falls back to built-in QuikUI templates if user templates not found
    5. Falls back to FastAPI's default JSON response if no templates found

    Args:
        app: The FastAPI application instance
        template_env: Optional Jinja2 Environment for custom error templates.
            If provided, will look for templates like HTTPException.html,
            RequestValidationError.html, etc. in your template directory.
            If not provided, uses QuikUI's minimal built-in templates.

    Example (with custom templates):
        >>> from fastapi import FastAPI
        >>> from fastapi.templating import Jinja2Templates
        >>> import quikui as qk
        >>>
        >>> app = FastAPI()
        >>> templates = Jinja2Templates(directory="templates")
        >>> qk.setup_error_handlers(app, template_env=templates.env)
        >>>
        >>> # Now create templates/HTTPException.html to customize error display

    Example (with built-in templates):
        >>> app = FastAPI()
        >>> qk.setup_error_handlers(app)  # Uses QuikUI's minimal default templates

    Template Context Variables:
        HTTPException templates receive:
            - exc: The exception object
            - status_code: HTTP status code (int)
            - status_text: Human-readable status text (str)
            - detail: Error detail message (str)

        RequestValidationError templates receive:
            - exc: The exception object
            - errors: List of ErrorDetail objects with loc, msg, type
            - status_code: HTTP status code (422)
            - status_text: "Validation Error"

    The error handlers will:
    - Catch all HTTPException instances (404, 403, etc.)
    - Catch RequestValidationError (422 validation errors)
    - Return templated HTML for HTMX requests
    - Return JSON for API requests
    - Support TemplatedHTTPException with custom HTMX targeting
    """
    global _error_template_env
    _error_template_env = template_env

    # Register exception handlers
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]


__all__ = [
    "ErrorDetail",
    "setup_error_handlers",
    "http_exception_handler",
    "validation_exception_handler",
]
