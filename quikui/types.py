from collections.abc import Callable
from typing import Any, cast, Annotated, Coroutine
from typing import ParamSpec, Protocol, TypeVar

from fastapi import Response

P = ParamSpec("P")
T = TypeVar("T")
MaybeAsyncFunc = Callable[P, T] | Callable[P, Coroutine[Any, Any, T]]

# FastAPI-specific
FastApiHandler = Callable[P, Coroutine[None, None, T | Response]]
FastApiDecorator = Callable[[MaybeAsyncFunc[P, T]], FastApiHandler]
