from functools import wraps, partial
import inspect
from typing import (
    Annotated,
    Any,
    ClassVar,
    Callable,
    get_args,
    Iterable,
    types,
)
from fastapi import Depends, Header, Request, Response
from fastapi.templating import Jinja2Templates
from fastapi.dependencies.utils import get_typed_return_annotation
from fastapi.responses import HTMLResponse
from jinja2 import Template, Environment
from pydantic import BaseModel

from .components import BaseComponent, Div
from .dependencies import QkVariant, RequestIfHtmlResponseNeeded
from .exceptions import HtmlResponseOnly, ResponseNotRenderable
from .types import P, T, MaybeAsyncFunc, FastApiHandler, FastApiDecorator
from .utils import append_to_signature, execute_maybe_sync_func, get_response


def render_component(
    html_only: bool = False,
    template: Template | str | None = None,
    env: Environment | Jinja2Templates | None = None,
    wrapper: Callable[[Iterable[BaseComponent]], BaseComponent] | None = None,
    wrapper_kwargs: dict | None = None,
) -> FastApiDecorator:
    """
    A decorator that should be used to automatically render an instance or sequence of
    :class:`~quikui.BaseComponent` subclass(es) into an :class:`~fastapi.responses.HTMLResponse`
    to respond to an incoming request that expects an HTML response (according to a heuristic).

    Args:
        html_only (bool):
            Whether this route should only accept Requests that expect an HTML response.
            Defaults to allowing both html and json responses, depending on heuristic detection.

        template (:class:`~jinja2.Template` | str | None):
            The template to use to render the model with using `result.model_dump()`.
            If it is a string, you **must** use the `env=` kwarg in tandem with it.
            Defaults to assuming return is a subclass of :class:`~quikui.BaseComponent`.

        env (:class:`~jinja2.Environment` | :class:`~fastapi.templating.Jinja2Templates` | None):
            The template environment that should be used to dynamically fetch a template to render
            with. Only is required if `template=` kwarg is a string value (the name of a template).

        wrapper:
            Function to use to wrap a sequence (e.g. ``list``) returned from a handler to
            transform it into an instance of :class:`~quikui.BaseComponent` for rendering.
            Defaults to :class:`~quikui.Div` for rendering a sequence result.

        **wrapper_kwargs:
            Keyword arguments to forward to constructing the model given in ``wrapper`` when
            rendering a sequence result (e.g. `return wrapper(*result, **wrapper_kwargs)`).

    Raises:
        :class:`~quikui.HtmlResponseOnly`:
            A 406 error if ``html_only`` is ``True`` and did not detect an HTML expected response.

        :class:`~quikui.ResponseNotRenderable`: If the result of evaluating the handler function is
            not an instance of str, :class:`~quikui.BaseComponent`, or
            a sequence of :class:`~quikui.BaseComponent`s, and no ``template`` is provided.

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

    # NOTE: We must create a getter for the template so that it is dynamically fetched when needed
    if isinstance(template, str):
        if env is None:
            raise AssertionError("`env=` must be set if `template=` is a str.")

        def get_template():
            return env.get_template(template)

    else:

        def get_template():
            return template  # type is `Template | None`

    def decorator(func: MaybeAsyncFunc[P, T]) -> FastApiHandler:
        @wraps(func)
        async def wrapper_render_if_html_requested(
            *args: P.args,
            __html_request: RequestIfHtmlResponseNeeded,
            qk_variant: QkVariant = None,
            **kwargs: P.kwargs,
        ) -> T | Response:
            if html_only and __html_request is None:
                raise HtmlResponseOnly()

            result = await execute_maybe_sync_func(func, *args, **kwargs)
            # NOTE: Short-circut to return response directly if our heuristic fails,
            #       or a user decides to return a direct Response object (bypassing our logic)
            if __html_request is None or isinstance(result, Response):
                return result

            # NOTE: Dependency resolves to a `Request` if we've made it this far
            request = __html_request
            if (response_template := get_template()) and isinstance(result, (BaseModel, dict)):
                result = response_template.render(
                    **(result.model_dump() if isinstance(result, BaseModel) else result),
                    request=request,
                    url_for=request.url_for,
                )

            elif (
                response_template
                and isinstance(result, (tuple, list))
                and all(isinstance(r, (BaseModel, dict)) for r in result)
            ):
                result = (wrapper if wrapper else Div)(  # type: ignore[operator]
                    *(
                        response_template.render(
                            **(r.model_dump() if isinstance(r, BaseModel) else r),
                            request=request,
                            url_for=request.url_for,
                        )
                        for r in result
                    ),
                    **(wrapper_kwargs or {}),
                )

            elif isinstance(result, (tuple, list)) and all(
                isinstance(r, (BaseComponent, str)) for r in result
            ):
                result = (wrapper if wrapper else Div)(  # type: ignore[operator]
                    *result,
                    **(wrapper_kwargs or {}),
                )

            elif not isinstance(result, (BaseComponent, str)):
                # NOTE: Should not happen if library is used properly
                raise ResponseNotRenderable(result)

            # NOTE: Needs `result` after processing
            if isinstance(result, BaseComponent):
                result = result.model_dump_html(  # type: ignore[assignment]
                    template_variant=qk_variant,
                    render_context=dict(request=request, url_for=request.url_for),
                )

            # else: `result` is assumed to be HTML str now (NOTE: could be unsafe)

            if response := get_response(kwargs):
                return HTMLResponse(result, headers=response.headers)

            else:
                return HTMLResponse(result)

        # NOTE: Ensure our html response detection dependency is included
        return append_to_signature(
            wrapper_render_if_html_requested,
            inspect.Parameter(
                "__html_request",
                inspect.Parameter.KEYWORD_ONLY,
                annotation=RequestIfHtmlResponseNeeded,
            ),
            inspect.Parameter(
                "qk_variant",
                inspect.Parameter.KEYWORD_ONLY,
                annotation=QkVariant,
                default=None,
            ),
        )

    return decorator
