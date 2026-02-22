from typing import Any

from fastapi import HTTPException, status
from jinja2 import Environment


class QuikUIError(Exception):
    """Base exception for all QuikUI errors."""

    pass


class TemplatedHTTPException(HTTPException):
    """
    HTTPException that can render itself using a Jinja2 template.

    Subclass this to create custom exceptions with rich HTML error pages.

    Example:
        >>> class TaskInProgressError(TemplatedHTTPException):
        ...     quikui_template_package_name = "myapp"
        ...     error_container = "#toast-container"  # Where to display the error
        ...     error_swap = "beforeend"              # How to insert the error
        ...
        ...     def __init__(self, task_title: str):
        ...         super().__init__(
        ...             status_code=409,
        ...             detail=f"Cannot delete task '{task_title}' while in progress"
        ...         )
        ...         self.task_title = task_title
        ...
        >>> # Create template: myapp/templates/TaskInProgressError.html
        >>> # Then raise: raise TaskInProgressError(task_title="My Task")
    """

    # Template configuration (same as BaseComponent)
    quikui_template_package_name: str = ""
    quikui_template_package_path: str = "templates"

    # HTMX error handling configuration
    error_container: str | None = (
        None  # CSS selector for error target (e.g., "#toast-container", "closest .error-container")
    )
    error_swap: str | None = None  # HTMX swap strategy (e.g., "innerHTML", "beforeend")
    template_variant: str | None = (
        None  # Template variant to use for rendering (e.g., "toast", "inline")
    )

    def model_dump_html(
        self,
        template_variant: str | None = None,
        env: Environment | None = None,
    ) -> str:
        """
        Render this exception as HTML using its template.

        Args:
            template_variant: Optional template variant (e.g., "toast", "inline")
            env: Optional Jinja2 environment to use

        Returns:
            Rendered HTML string
        """
        from .components import BaseComponent

        # Get the environment (reuse BaseComponent's logic)
        if env is None:
            # Create a temporary component class to get the environment
            class _TempComponent(BaseComponent):
                quikui_template_package_name = self.quikui_template_package_name
                quikui_template_package_path = self.quikui_template_package_path

            env = _TempComponent.quikui_environment()

        # Find template
        template_name = self.__class__.__name__
        if template_variant:
            template_name = f"{template_name}.{template_variant}"
        template_name = f"{template_name}.html"

        try:
            template = env.get_template(template_name)
        except Exception:
            # Fall back to simple rendering if template not found
            return f"<p>{self.detail}</p>"

        # Build context from exception attributes
        context = {
            "status_code": self.status_code,
            "detail": self.detail,
            "headers": getattr(self, "headers", None),
        }

        # Add all public attributes to context
        for key, value in self.__dict__.items():
            if not key.startswith("_"):
                context[key] = value

        return template.render(**context)


class NoTemplateFoundError(QuikUIError, RuntimeError):
    def __init__(self, cls: type, template_variant: str | None):
        if template_variant:
            template_name = f"{cls.__name__}.{template_variant}.html"
        else:
            template_name = f"{cls.__name__}.html"

        super().__init__(
            f"Component '{cls.__name__}' does not contain an environment with a template "
            f"named '{template_name}' in it, or subclass another component that can render itself."
        )


class HtmlResponseOnlyError(QuikUIError, HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail="This route can only provide HTML responses. Please set Accept headers.",
        )


class ResponseNotRenderableError(QuikUIError, ValueError):
    def __init__(self, result: Any):
        super().__init__(
            "Result type must either be an HTML-safe string, an instance of a BaseComponent "
            f"subclass, or an iterable of BaseComponent subclasses, not {type(result)}."
        )


__all__ = [
    "QuikUIError",
    "HtmlResponseOnlyError",
    "NoTemplateFoundError",
    "ResponseNotRenderableError",
    "TemplatedHTTPException",
]
