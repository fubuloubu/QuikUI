from typing import Annotated
from pydantic import BaseModel, ValidationError
from fastapi import Request, Depends, Header


# HTMX Headers
HxRequest = Annotated[bool, Header(include_in_schema=False)]
# QuikUI Headers (this library)
QkVariant = Annotated[str | None, Header(include_in_schema=False)]


def request_if_html_response_needed(
    request: Request,
    # Header fields to detect with
    accept: Annotated[str | None, Header(include_in_schema=False)] = None,
    content_type: Annotated[str | None, Header(include_in_schema=False)] = None,
    hx_request: HxRequest = False,
    qk_variant: QkVariant = None,
) -> Request | None:
    """
    FastAPI dependency to detect if an ``HTMLResponse`` should be given to ``request``.
    Uses a serious of Header-based heuristics to determine if required.

    Returns:
        (Request | None): feedsback the request it was given if the detection triggers.
            Defaults to None (no HTML Request detected).
    """
    if hx_request or qk_variant:
        # We definitely know if any of these headers are present, it means respond w/ html
        return request

    elif content_type == "application/json":
        # Assume that if the request is JSON, the response should be too
        # NOTE: htmx never does this
        return None

    elif accept is not None and (accepted_types := list(t.strip() for t in accept.split(","))):
        if any(t.startswith("text/html") for t in accepted_types):
            return request  # We have determined this is expecting HTML back

    # else: We haven't determined (according to above heuristics) that HTML is requested
    return None


RequestIfHtmlResponseNeeded = Annotated[Request | None, Depends(request_if_html_response_needed)]
