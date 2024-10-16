from pydantic import BaseModel
from typing import Self
from pydantic import BaseModel, ValidationError
from fastapi import Request
from starlette.datastructures import FormData
from fastapi.exceptions import RequestValidationError


def unflatten(form_data: FormData) -> dict:
    return {key: value for key, value in form_data.items()}


class FormModel(BaseModel):
    @classmethod
    async def as_form(cls, request: Request) -> Self:
        async with request.form() as form_data:
            model_data = unflatten(form_data)

        try:
            return cls.model_validate(model_data)

        except ValidationError as e:
            raise RequestValidationError(
                e.errors(include_input=True, include_url=True, include_context=True)
            )
