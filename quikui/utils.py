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


def get_hx_request(
    request: Request, hx_request: Annotated[str | None, Header()] = None
) -> Request | None:
    """
    FastAPI dependency that returns the current request if it is an HTMX one,
    i.e. it contains an `"HX-Request: true"` header.
    """
    return request if hx_request == "true" else None


DependsHXRequest = Annotated[Request | None, Depends(get_hx_request)]


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
