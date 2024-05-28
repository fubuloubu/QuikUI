from functools import wraps, partial
import inspect
from typing import (
    Annotated,
    Any,
    ClassVar,
    Callable,
    Coroutine,
    get_args,
    GenericAlias,
    _GenericAlias,
    types,
)
from fastapi import (
    HTTPException,
    Depends,
    Header,
    Request,
    status,
    Response,
)
from fastapi.dependencies.utils import get_typed_return_annotation
from fastapi.responses import HTMLResponse

from .components import BaseComponent
from .utils import (
    DependsHtmlResponse,
    append_to_signature,
    execute_maybe_sync_func,
    MaybeAsyncFunc,
    P,
    T,
    get_response,
)


def render_component(
    html_only: bool = False,
    # render_model: BaseComponent | None = None,
) -> Callable[[MaybeAsyncFunc[P, T]], Callable[P, Coroutine[None, None, T | Response]]]:
    """
    A decorator that should be used to automatically render an instance or sequence of
    :class:`~quikui.BaseComponent` subclass(es) into an :class:`~fastapi.responses.HTMLResponse`
    to respond to an incoming request that expects an HTML response.

    Args:
        html_only (bool):
            Whether this route should only accept Requests that expect an HTML response.

    Raises:
        :class:`~fastapi.HTTPException`:
            A 406 error if ``html_only`` is ``True`` and did not detect an HTML expected response.
        ValueError: If the result of executing the function is not an instance of str,
            :class:`~quikui.BaseComponent`, or Iterable[:class:`~fastapi.BaseComponent`].

    Usage example::

        >>> import quikui as qk
        >>>
        >>> app = FastAPI()
        >>>
        >>>
        >>> @app.get("/path")
        >>> @qk.render_component()
        >>> def get_something():
        >>>     return instance_of_basecomponent_subclass  # Automatically converted to html


    ```note
    Errors are only raised when the decorated function is called. Any unexpected error will
    generate a 500 Server Error in your FastAPI app.
    ```
    """

    def decorator(
        func: MaybeAsyncFunc[P, T],
    ) -> Callable[P, Coroutine[None, None, T | Response]]:

        @wraps(func)
        async def wrapper_render_if_html_requested(
            *args: P.args,
            __html_response_requested: DependsHtmlResponse,
            **kwargs: P.kwargs,
        ) -> T | Response:
            if html_only and __html_response_requested is None:
                raise HTTPException(
                    status.HTTP_406_NOT_ACCEPTABLE,
                    "This route can only provide HTML responses. Please set Accept headers.",
                )

            result = await execute_maybe_sync_func(func, *args, **kwargs)
            if __html_response_requested is None or isinstance(result, Response):
                return result

            if (render_model := get_typed_return_annotation(func)) and isinstance(
                render_model, (GenericAlias, _GenericAlias, types.UnionType)
            ):
                # List[...] or list[...] or Tuple[...] or tuple[...]
                render_model = get_args(render_model)[0]
                # NOTE: `get_args() returns either (Class,) or (Class, None)

            # else: `render_model` is None, which is okay

            if isinstance(result, BaseComponent):
                result = (
                    render_model.template.render(**result.model_dump())
                    if render_model is not None
                    else result.model_dump_html()
                )

            elif isinstance(result, (tuple, list)) and all(
                isinstance(r, BaseComponent) for r in result
            ):
                result = "".join(
                    (
                        render_model.template.render(**r.model_dump())
                        if render_model is not None
                        else r.model_dump_html()
                    )
                    for r in result
                )

            elif not isinstance(result, str):
                # NOTE: Should not happen if library is used properly, will raise 500 server exception
                raise ValueError(
                    "Result must either be an HTML string,"
                    "an instance of a BaseComponent subclass, "
                    "or an iterable of BaseComponent subclasses."
                )

            # else: `result` is str, assume it is HTML

            if response := get_response(kwargs):
                return HTMLResponse(result, headers=response.headers)

            else:
                return HTMLResponse(result)

        # NOTE: Ensure our html response detection dependency is included
        return append_to_signature(
            wrapper_render_if_html_requested,
            inspect.Parameter(
                "__html_response_requested",
                inspect.Parameter.KEYWORD_ONLY,
                annotation=DependsHtmlResponse,
            ),
        )

    return decorator
