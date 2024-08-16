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
from jinja2 import Template
from pydantic import BaseModel

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
    template: Template | None = None,
) -> Callable[[MaybeAsyncFunc[P, T]], Callable[P, Coroutine[None, None, T | Response]]]:
    """
    A decorator that should be used to automatically render an instance or sequence of
    :class:`~quikui.BaseComponent` subclass(es) into an :class:`~fastapi.responses.HTMLResponse`
    to respond to an incoming request that expects an HTML response (according to a heuristic).

    Args:
        html_only (bool):
            Whether this route should only accept Requests that expect an HTML response.
            Defaults to allowing both html and json responses, depending on heuristic detection.

        template (:class:`~jinja2.Template` | None):
            The template to use to render the model with using `result.model_dump()`.
            Defaults to assuming return is a subclass of :class:`~quikui.BaseComponent`.

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
        >>> @app.get("/path")
        >>> @qk.render_component()
        >>> def get_something():
        >>>     return instance_of_basecomponent_subclass  # Automatically converted to HTMLResponse


    ```{warning}
    If using the ``template`` keyword argument, please note that the result model is dumped using
    the normal Pydantic `.model_dump` method and therefore will not contain any extra attributes
    or classes that QuikUI provides.
    ```

    ```{warning}
    Errors are only raised when the decorated function is called.
    Any unexpected error will generate a 500 Server Error in your FastAPI app.
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

            if template and isinstance(result, BaseModel):
                result = template.render(**result.model_dump())

            elif (
                template
                and isinstance(result, (tuple, list))
                and all(isinstance(r, BaseModel) for r in result)
            ):
                result = "".join(
                    template.render(**r.model_dump()) for r in result
                )

            elif isinstance(result, BaseComponent):
                result = result.__html__()  # NOTE: `__html__` is suggested for defaults

            elif isinstance(result, (tuple, list)) and all(
                isinstance(r, BaseComponent) for r in result
            ):
                result = "".join(
                    r.__html__() for r in result
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
