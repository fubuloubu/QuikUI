from collections.abc import Callable
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from markupsafe import Markup

if TYPE_CHECKING:
    from collections.abc import Iterable

    from jinja2 import Environment

    from .components import BaseComponent

# Context variable to store the current template context provider
_context_provider: ContextVar[Callable[[], dict[str, Any]] | None] = ContextVar(
    "_context_provider", default=None
)


def set_context_provider(provider: Callable[[], dict[str, Any]] | None):
    """
    Set a function that provides global context for all component templates.

    The provider function will be called whenever a component is rendered to HTML,
    and its return value will be merged into the template context.

    This is useful for injecting framework-specific values like FastAPI's request,
    or application-specific values like the session's current user.

    Usage with FastAPI:

        from fastapi import Request
        from starlette.middleware.base import BaseHTTPMiddleware
        import quikui as qk

        class QuikUIContextMiddleware(BaseHTTPMiddleware):

            # Use FastAPI's dependency injection via request args here
            async def dispatch(self, request: Request, call_next):

                # load other things here like sessions values
                current_user = await get_current_user(request)

                # Set up context provider for this request
                def context_provider():
                    return {
                        "request": request,
                        "url_for": request.url_for,
                        "current_user": current_user,
                    }

                qk.set_context_provider(context_provider)

                return await call_next(request)

        app.add_middleware(QuikUIContextMiddleware)

    Now in component templates, you can access request, url_for, and current_user:

        <a href="{{ url_for('home') }}">Home</a>

        {% if current_user.is_admin %}
            <button>Admin Panel</button>
        {% endif %}

    Args:
        provider: A callable that returns a dict of context variables, or None to clear the provider
    """
    _context_provider.set(provider)


def get_template_context() -> dict[str, Any]:
    """
    Get the current template context from the provider.

    Returns:
        A dictionary of context variables, or an empty dict if no provider is set
    """

    if not (provider := _context_provider.get()):
        return {}

    return provider()


def render_component_variant(
    component_or_list: "BaseComponent | Iterable[BaseComponent]",
    variant: str,
):
    """
    Jinja2 filter for rendering component variants.

    Supports rendering a single component or a list of components with the same variant.

    Args:
        component_or_list: A QuikUI BaseComponent instance or list/iterable of instances
        variant: template variant name (e.g., "table", "list", "form")

    Returns:
        Markup: Safe HTML string ready for rendering

    Example:
        {{ complaint|variant("table") }}
        {{ user|variant("card") }}
        {{ complaints|variant("table") }}  # Renders all complaints as table rows
    """

    from .components import BaseComponent

    # Single component
    if isinstance(component_or_list, BaseComponent):
        return Markup(component_or_list.model_dump_html(template_variant=variant))

    return Markup(
        "".join(
            component.model_dump_html(template_variant=variant) for component in component_or_list
        )
    )


def register_filters(env: "Environment"):
    """
    Register QuikUI Jinja2 filters on a Jinja2 Environment.

    This adds the following filters:
    - variant: Render a component with an optional variant

    Usage with FastAPI:
        from fastapi.templating import Jinja2Templates
        import quikui as qk

        templates = Jinja2Templates(directory="templates")
        qk.register_filters(templates.env)

        # In templates:
        {{ component|variant("table") }}

    Args:
        env: A Jinja2 Environment instance
    """
    env.filters["variant"] = render_component_variant
