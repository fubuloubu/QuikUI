from typing import Callable, Type, TYPE_CHECKING
from pydantic import ValidationError
from fastapi import Request, Depends
from starlette.datastructures import FormData
from fastapi.exceptions import RequestValidationError

if TYPE_CHECKING:
    from .components import FormModel


def unflatten(form_data: FormData) -> dict:
    return {key: value for key, value in form_data.items()}


def form_handler(Model: Type["FormModel"]):
    async def handle_request(request: Request) -> "FormModel":
        async with request.form() as form_data:
            model_data = unflatten(form_data)

        try:
            return Model.model_validate(model_data)
        except ValidationError as e:
            raise RequestValidationError(
                e.errors(include_input=False, include_url=False, include_context=False)
            )

    return handle_request
