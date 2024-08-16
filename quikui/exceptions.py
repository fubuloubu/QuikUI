from fastapi import HTTPException, status
from typing import Any, Type


class BaseException(Exception):
    pass


class NoTemplateFound(BaseException, RuntimeError):
    def __init__(self, cls: Type, template_variant: str | None):
        if template_variant:
            template_name = f"{cls.__name__}.{template_variant}.html"
        else:
            template_name = f"{cls.__name__}.html"

        super().__init__(
            f"Component '{cls.__name__}' does not contain an environment with a template "
            f"named '{template_name}' in it, or subclass another component that can render itself."
        )


class HtmlResponseOnly(BaseException, HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail="This route can only provide HTML responses. Please set Accept headers.",
        )


class ResponseNotRenderable(BaseException, HTTPException):
    def __init__(self, result: Any):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Result type must either be an HTML-safe string, "
                "an instance of a BaseComponent subclass, "
                "or an iterable of BaseComponent subclasses, "
                f"not {type(result)}."
            ),
        )


__all__ = [
    HtmlResponseOnly.__name__,
    NoTemplateFound.__name__,
    ResponseNotRenderable.__name__,
]
