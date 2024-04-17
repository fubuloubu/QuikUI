from functools import wraps, partial
import inspect
from typing import Annotated, Any, ClassVar, Callable, Coroutine
from fastapi import (
    HTTPException,
    Depends,
    Header,
    Request,
    status,
    Response,
)
from fastapi.responses import HTMLResponse

from .components import BaseComponent, Page
from .utils import (
    DependsHXRequest,
    append_to_signature,
    execute_maybe_sync_func,
    MaybeAsyncFunc,
    P,
    T,
    get_response,
)


def render_component(
    html_only: bool = False,
    is_page: bool = False,
) -> Callable[[MaybeAsyncFunc[P, T]], Callable[P, Coroutine[None, None, T | Response]]]:

    def decorator(
        func: MaybeAsyncFunc[P, T],
    ) -> Callable[P, Coroutine[None, None, T | Response]]:

        if is_page:

            @wraps(func)
            async def wrapper_render_page(
                *args: P.args,
                __page_request: Request,
                **kwargs: P.kwargs,
            ) -> T | Response:
                result = await execute_maybe_sync_func(func, *args, **kwargs)
                if isinstance(result, Response):
                    return result

                elif __page_request is None:  # or not isinstance(result, Page):
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                        "This component must be rendered from a page request.",
                    )

                response = get_response(kwargs)
                return HTMLResponse(
                    result.model_dump_html(),
                    headers=None if response is None else response.headers,
                )

            return append_to_signature(
                wrapper_render_page,
                inspect.Parameter(
                    "__page_request",
                    inspect.Parameter.KEYWORD_ONLY,
                    annotation=Request,
                ),
            )

        else:

            @wraps(func)
            async def wrapper_render_if_htmx(
                *args: P.args,
                __hx_request: DependsHXRequest,
                **kwargs: P.kwargs,
            ) -> T | Response:
                if html_only and __hx_request is None:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        "This route can only process HTMX requests.",
                    )

                result = await execute_maybe_sync_func(func, *args, **kwargs)
                if __hx_request is None or isinstance(result, Response):
                    return result

                elif isinstance(result, BaseComponent):
                    result = result.model_dump_html()

                elif not isinstance(result, str):
                    # NOTE: Should not happen if library is used properly
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                        "Function does not render properly.",
                    )

                response = get_response(kwargs)
                return HTMLResponse(
                    result,
                    headers=None if response is None else response.headers,
                )

            return append_to_signature(
                wrapper_render_if_htmx,
                inspect.Parameter(
                    "__hx_request",
                    inspect.Parameter.KEYWORD_ONLY,
                    annotation=DependsHXRequest,
                ),
            )

    return decorator
