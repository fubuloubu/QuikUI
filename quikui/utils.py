import inspect
from asyncio import iscoroutinefunction
from collections.abc import Callable, Mapping
from typing import Any, cast, Annotated, Coroutine
from typing import ParamSpec, Protocol, TypeVar

from fastapi import Request, Response


from fastapi import Response, Request, Header, Depends
from fastapi.concurrency import run_in_threadpool

P = ParamSpec("P")
T = TypeVar("T")
MaybeAsyncFunc = Callable[P, T] | Callable[P, Coroutine[Any, Any, T]]


def html_response_requested(
    request: Request,
    hx_request: Annotated[bool, Header()] = False,
    content_type: Annotated[str | None, Header()] = None,
    raw_accept_header: Annotated[str | None, Header(alias="accept")] = None,
) -> Request | None:
    if hx_request:
        # We definitely know that HX-Request=true headers means return html
        return request

    elif content_type and content_type == "application/json":
        # Assume that if the request is JSON, the response should be too
        # NOTE: htmx never does this
        return None

    elif raw_accept_header and (
        accepted_types := list(t.strip() for t in raw_accept_header.split(","))
    ):
        if any(t.startswith("text/html") for t in accepted_types):
            return request  # We have determined this is expecting HTML back

    # else: We haven't determined (according to above heuristics) that HTML is requested
    return None


DependsHtmlResponse = Annotated[Request | None, Depends(html_response_requested)]


def append_to_signature(func: Callable, *params: inspect.Parameter) -> Callable:
    """
    Appends the given parameters to the *end* of the signature of the given function.

    Notes:
        - This method does not change the function's arguments, it only makes FastAPI's
        dependency resolution system recognize inserted parameters.
        - This is *not* a general purpose method, it is strongly recommended to only
        append keyword-only parameters that have "unique" names that are unlikely to
        be already in the function's signature.

    Arguments:
        func: The function whose signature should be extended.
        params: The parameters to add to the function's signature.

    Returns:
        The received function with an extended `__signature__`.
    """
    signature = inspect.signature(func)
    func.__signature__ = signature.replace(parameters=(*signature.parameters.values(), *params))  # type: ignore[attr-defined]
    return func


async def execute_maybe_sync_func(
    func: MaybeAsyncFunc[P, T], *args: P.args, **kwargs: P.kwargs
) -> T:
    """
    Executes the given function in a thread if it's a sync one, or in the current asyncio
    event loop if it's an async one.

    Arguments:
        func: The function to execute.
        *args: Positional arguments to pass to the function.
        **kwargs: Keyword arguments to pass to the function.
    """
    if iscoroutinefunction(func):
        return await func(*args, **kwargs)  # type: ignore[no-any-return]

    return await run_in_threadpool(cast(Callable[P, T], func), *args, **kwargs)


def get_response(kwargs: Mapping[str, Any]) -> Response | None:
    """
    Returns the first `Response` instance from the values in `kwargs` (if there is one).

    Arguments:
        kwargs: The keyword arguments from which the `Response` should be returned.
    """
    for val in kwargs.values():
        if isinstance(val, Response):
            return val

    return None
