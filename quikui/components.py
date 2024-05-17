from typing import Annotated, Any, ClassVar, Callable, Literal, Type, Iterator
from itertools import chain
from functools import cache
from enum import Enum
import inspect

from jinja2 import Environment, PackageLoader, TemplateNotFound
from pydantic import BaseModel, Field, model_validator
from pydantic.fields import FieldInfo
from pydantic import ValidationError

from fastapi.exceptions import RequestValidationError


def is_component(value: Any) -> bool:
    return isinstance(value, BaseComponent)


class BaseComponent(BaseModel):
    # NOTE: If you want to define custom components using your own templates,
    #       override this to your package name (must be stored in `./templates`)
    html_template_package: ClassVar[str] = "quikui"

    @classmethod
    @property
    @cache
    def env(cls):
        env = Environment(
            loader=PackageLoader(cls.html_template_package),
            autoescape=True,
        )
        env.filters.update({"is_component": is_component})
        return env

    @property
    def template(self):
        # NOTE: Will only function with components from this library,
        #       unless `.initialize` is overriden
        if self.env is None:
            raise ValueError(
                "Your component classes need to be initialized with a template"
            )

        template_class = self.__class__
        while issubclass(template_class, BaseComponent):
            try:
                return self.env.get_template(f"{template_class.__name__}.html")

            except TemplateNotFound:
                # NOTE: Potentially dangerous if multi-class heirarchy exists, only uses first
                template_class = template_class.__base__

        raise ValueError(
            f"Component '{self.__class__.__name__}' does not subclass"
            " a component with a valid template."
        )

    def model_dump_html(self, *args, **kwargs) -> str:
        model_dict = self.model_dump(*args, **kwargs)
        return self.template.render(**model_dict)


class Page(BaseComponent):
    title: str
    content: list[BaseComponent]


class Heading(BaseComponent):
    content: str | BaseComponent
    level: Annotated[int, Field(strict=True, ge=1, le=5)] = 1


class Paragraph(BaseComponent):
    content: str | BaseComponent


class Break(BaseComponent):

    def model_dump_html(self) -> str:
        return "<br>"


class TargetType(str, Enum):
    SAME_FRAME = "_self"
    NEW_WINDOW = "_blank"
    PARENT_FRAME = "_parent"
    FULL_BODY = "_top"

    def __str__(self) -> str:
        return self._value_


class Anchor(BaseComponent):
    route: str
    content: str | BaseComponent
    target: TargetType | str = TargetType.SAME_FRAME


class RequestType(str, Enum):
    GET = "get"
    POST = "post"
    PUT = "put"
    PATHC = "patch"
    DELETE = "delete"

    def __str__(self) -> str:
        return self._value_


class Button(BaseComponent):
    route: str
    content: str | BaseComponent
    verb: RequestType = RequestType.GET


class _MultiItemComponent(BaseComponent):
    items: list[str | BaseComponent] = []

    def __init__(self, *args: BaseComponent) -> None:
        if not isinstance(args, (str, BaseComponent)) and (
            isinstance(args, (tuple, list))
            and not all(isinstance(c, (str, BaseComponent)) for c in args)
        ):
            raise ValueError(
                "Must provide either BaseComponent or list of BaseComponents."
            )

        super().__init__(items=list(args))


class Div(_MultiItemComponent):
    pass


class Span(_MultiItemComponent):
    pass


class List(_MultiItemComponent):
    pass


class Image(BaseComponent):
    source: str


class InputType(str, Enum):
    TEXT = "text"
    EMAIL = "email"
    PASSWORD = "password"
    SELECT = "select"
    SUBMIT = "submit"
    RESET = "reset"
    CHECKBOX = "checkbox"
    RADIO = "radio"

    def __str__(self) -> str:
        return self._value_


class FormInput(BaseComponent):
    id: str | None = None
    type: Literal[InputType]
    label: str | BaseComponent | None = None
    add_break: bool = False
    required: bool = True

    @classmethod
    def from_model_field(cls, field_name: str, field_info: FieldInfo) -> "FormInput":
        return cls(
            id=field_name, **field_info.json_schema_extra.get("form_attributes", {})
        )


class TextInput(FormInput):
    type: Literal[InputType] = InputType.TEXT


class EmailInput(FormInput):
    type: Literal[InputType] = InputType.EMAIL


class PasswordInput(FormInput):
    type: Literal[InputType] = InputType.PASSWORD


class InputOption(BaseModel):
    value: str
    label: str | BaseComponent


class InputWithOptions(FormInput):
    options: list[InputOption] = []

    @classmethod
    def from_model_field(cls, field_name: str, field_info: FieldInfo) -> "FormInput":
        form_attributes = field_info.json_schema_extra.get("form_attributes", {})

        # NOTE: Override to allow adding options directly from enum field annotation
        if "options" not in form_attributes and issubclass(field_info.annotation, Enum):
            form_attributes["options"] = [
                InputOption(label=option.value, value=option.value)
                for option in field_info.annotation
            ]

        return cls(id=field_name, **form_attributes)
        # NOTE: Can add options later via `self.options.extend(...)`


class SelectionInput(InputWithOptions):
    type: Literal[InputType] = InputType.SELECT
    # NOTE: Can set these after the initialization
    selected: str | None = None
    disabled: set[str] = {}

    @model_validator(mode="after")
    def check_selected_disabled(self) -> "SelectionInput":
        option_values = set(option.value for option in self.options)

        if self.selected and self.selected not in option_values:
            raise ValidationError("Selected must be one of the current options.")

        if not self.disabled.issubset(option_values):
            raise ValidationError("All disabled options should be current options.")

        return self


class CheckboxInput(FormInput):
    type: Literal[InputType] = InputType.CHECKBOX


class RadioInput(InputWithOptions):
    type: Literal[InputType] = InputType.RADIO


class SubmitForm(FormInput):
    type: Literal[InputType] = InputType.SUBMIT


class ResetForm(FormInput):
    type: Literal[InputType] = InputType.RESET


class Form(BaseComponent):
    id: str | None = None
    verb: RequestType = RequestType.POST
    route: str
    items: list[BaseComponent]


class FormModel(BaseModel):

    @classmethod
    def create_form_input(
        cls,
        field_name: str,
    ) -> FormInput:
        if not (field_info := cls.model_fields.get(field_name)):
            raise ValueError

        if not (input_class := field_info.json_schema_extra.get("form_type")):
            raise ValueError

        return input_class.from_model_field(field_name, field_info)

    @classmethod
    def create_form_items(cls) -> Iterator[BaseComponent]:
        for field_name in cls.model_fields:
            yield cls.create_form_input(field_name)
            yield Break()

        yield SubmitForm()

    @classmethod
    def create_form(
        cls,
        route: str,
        id: str | None = None,
        verb: RequestType = RequestType.POST,
    ) -> Form:
        return Form(
            route=route,
            id=id,
            verb=verb,
            items=list(cls.create_form_items()),
        )


__all__ = [
    BaseComponent.__name__,
    Page.__name__,
    Heading.__name__,
    Paragraph.__name__,
    Break.__name__,
    TargetType.__name__,
    Anchor.__name__,
    RequestType.__name__,
    Button.__name__,
    Div.__name__,
    Span.__name__,
    List.__name__,
    Form.__name__,
    FormInput.__name__,
    InputType.__name__,
    TextInput.__name__,
    EmailInput.__name__,
    PasswordInput.__name__,
    SelectionInput.__name__,
    InputOption.__name__,
    CheckboxInput.__name__,
    RadioInput.__name__,
    SubmitForm.__name__,
    FormModel.__name__,
]
