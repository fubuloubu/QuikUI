from collections.abc import AsyncGenerator, Callable
from typing import Any, Coroutine
from typing import ParamSpec, TypeVar

from fastapi import Response

P = ParamSpec("P")
T = TypeVar("T")
MaybeAsyncFunc = (
    Callable[P, T]
    | Callable[P, Coroutine[Any, Any, T] | Callable[P, AsyncGenerator[T]]]
)

# FastAPI-specific
FastApiHandler = Callable[P, Coroutine[None, None, T | Response]]
FastApiDecorator = Callable[[MaybeAsyncFunc[P, T]], FastApiHandler]
