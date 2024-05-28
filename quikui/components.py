import string
from typing import (
    Annotated,
    Any,
    ClassVar,
    Callable,
    List,
    Literal,
    Type,
    Iterator,
    Dict,
    Set,
)
from collections.abc import Container
from itertools import chain
from functools import cache
from enum import Enum
import inspect

from markupsafe import Markup
from jinja2 import Environment, PackageLoader, TemplateNotFound, Template
from pydantic import (
    BaseModel,
    Field,
    model_validator,
    model_serializer,
    field_validator,
    RootModel,
)
from pydantic.fields import FieldInfo
from pydantic import ValidationError

from fastapi.exceptions import RequestValidationError

# NOTE: https://html.spec.whatwg.org/multipage/syntax.html#attributes-2
VALID_ATTR_CHARS = set(string.printable) - set(""" "'`<>/=""")


def is_component(value: Any) -> bool:
    return isinstance(value, BaseComponent)


class CssClasses(RootModel):
    root: Set[str] = {}

    def update(self, other):
        if isinstance(other, CssClasses):
            self.root.update(other.root)
        else:
            self.root.update(other)

    def __bool__(self) -> bool:
        return bool(self.root)

    @model_validator(mode="after")
    def validate_markup_safe(self):
        assert all(
            set(item).issubset(VALID_ATTR_CHARS) for item in self.root
        ), "Not in spec"
        return self

    @model_serializer()
    def serialize_css_classes(self) -> str:
        return " ".join(self.root)


class Attributes(RootModel):
    root: Dict[str, str | bool] = {}

    def __getitem__(self, key):
        return self.root.__getitem__(key)

    def __setitem__(self, key, val):
        return self.root.__setitem__(key, val)

    def update(self, other):
        if isinstance(other, Attributes):
            self.root.update(other.root)
        else:
            self.root.update(other)

    def __bool__(self) -> bool:
        return bool(self.root)

    @model_validator(mode="after")
    def validate_markup_safe(self):
        assert "class" not in self.root, "Can't set `class` via attributes"
        assert all(
            set(key).issubset(VALID_ATTR_CHARS) for key in self.root
        ), "Not in spec"
        assert all(
            set(value).issubset(set(string.printable)) for value in self.root.values()
        ), "Not in spec"
        return self

    @model_serializer()
    def serialize_html_attributes(self) -> str:
        return Markup(
            " ".join(
                (f'{k}="{v}"' if not isinstance(v, bool) else k)
                for k, v in self.root.items()
                if v  # Relies on truthiness to render bools and strings correctly
            )
        )


class BaseComponent(BaseModel):
    """
    A subclass of `pydantic.BaseModel` that supports serialization to "safe" HTML. Serialization
    to HTML is either done by parsing a Jinja2 template (distributed with the package), or by
    explicitly overriding the `model_dump_html` function in a subclass. It is assumed that you
    take great care to properly handle user-generated content by "escaping" (making it safe).

    https://htmx.org/essays/web-security-basics-with-htmx/#always-use-an-auto-escaping-template-engine
    """

    html_template_package: ClassVar[str] = "quikui"
    """The package that should be used to search for templates for components that do not
    override `model_dump_html`. If you want to define custom components using your own templates,
    override this in your base class to your package name. It is assumed the templates are stored
    in a `./templates` package resource folder. Defaults to this package."""

    __quikui_component_name__: ClassVar[str | None] = None
    """To override the value of ``__component_name__`` when rendering the component."""

    css: CssClasses = Field(default_factory=CssClasses, exclude=True)
    """Add extra CSS classes to this component. Useful for integration with your design system."""

    attrs: Attributes = Field(default_factory=Attributes, exclude=True)
    """Add extra attributes to this component. Exposed to template rendering as
    ``__extra_attrs__``."""

    @classmethod
    @property
    @cache
    def env(cls) -> Environment:
        """
        The environment to search for templates for this class and all it's subclasses.

        ```note
        This property is cached.
        ```
        """
        env = Environment(
            loader=PackageLoader(cls.html_template_package),
            autoescape=True,
        )
        env.filters.update({"is_component": is_component})
        return env

    @classmethod
    @property
    def template(cls) -> Template:
        """
        The template that should be used to render this model.
        """
        template_class = cls
        while issubclass(template_class, BaseComponent):
            try:
                return template_class.env.get_template(
                    f"{template_class.__name__}.html"
                )

            except TemplateNotFound:
                # NOTE: Potentially dangerous if multi-class heirarchy exists, only uses first
                template_class = template_class.__base__

        # NOTE: If we get to this class, there was some error in user's subclassing system
        raise ValueError(
            f"Component '{cls.__name__}' does not subclass a component with a valid template."
        )

    def model_dump_html(
        self,
        include: Container | None = None,
        exclude: Container | None = None,
        **kwargs: dict,
    ) -> str:
        """
        Serialize this model to "safe" HTML. This default implementation assumes that a template
        exists for this model in `Class.env` that can be used to serialize this model by it's top-
        level fields, including computed fields and any other fields that should be included.

        Args:

            include: Fields to include that would otherwise be skipped.
            exclude: Fields that shold be skipped which would otherwise be included.
            **kwargs: Any other modifiers you need to pass to serialization.

        ```note
        You can override this if you can directly return "safe" html without using a template.
        ```

        ```warning
        This only gets the top-level current values, any recursion will be done via templating to
        ensure Markup safety context is bubbled up correctly. So, we do not pass down the further
        recursive context from `include` or `exclude` kwargs.
        ```
        """
        if not include:
            include = set()

        if not exclude:
            exclude = set()

        model_dict = dict(
            (f, getattr(self, f))
            # NOTE: Ensure we get all public, computed, and any requested private fields...
            for f in chain(self.model_fields, self.model_computed_fields, include)
            #       ...but also allow skipping fields we don't need for template context.
            if f not in exclude and f not in ("css", "attrs")
        )

        attrs = self.attrs.copy()

        if self.css:
            attrs["class"] = self.css.model_dump()

        if attrs:
            model_dict["__extra_attrs__"] = attrs.model_dump()

        model_dict["__component_name__"] = (
            self.__quikui_component_name__ or self.__class__.__name__
        )

        return self.template.render(**model_dict)

    def __html__(self) -> str:
        """
        Serialize this model to "safe" HTML, using default settings for field include/exclude.
        This should not be overriden, except to modify how `model_dump_html` gets called by Jinja2.

        ```note
        This allows `BaseComponent` models to automatically serialize themselves as HTML when used
        in a Jinga2 template. We can include private fields for the template engine this way.
        ```
        """
        return self.model_dump_html()


class Heading(BaseComponent):
    content: str | BaseComponent
    level: Annotated[int, Field(strict=True, ge=1, le=5)] = 1


class _SingleContentComponent(BaseComponent):
    content: str | BaseComponent


class Paragraph(_SingleContentComponent):
    __quikui_component_name__ = "p"


class Break(BaseComponent):
    def model_dump_html(self, **kwargs) -> str:
        return "<br>"


class Anchor(BaseComponent):
    __quikui_component_name__ = "a"
    route: str
    content: str | BaseComponent


class Button(_SingleContentComponent):
    pass


class _MultiItemComponent(BaseComponent):
    items: list[str | BaseComponent] = []


class Div(_MultiItemComponent):
    pass


class Span(_MultiItemComponent):
    pass


class ListItem(_SingleContentComponent):
    __quikui_component_name__ = "li"
    content: str | BaseComponent


class _ListComponent(_MultiItemComponent):
    """
    Component class that renders as a list component, with the inner content wrapped as `li`
    elements. Implemented in such as a way that you can get correct type hints on what it returns
    in the normal case where JSON is rendered, making it easy to use for both API and HTML modes.

    Usage example::

        >>> @app.get("/items")
        >>> @qk.render_component()
        >>> def get_items() -> list[MyItem]:  # What it returns in JSON mode
        >>>     return qk.UnorderedList(items=session.exec(select(MyItem)).all())

    ```note
    You can add a common set of css classes or attributes to the inner list items by specifying
    ``item_css=set(...)`` and/or ``item_attributes=dict(...)`` to the class initialization. You
    can also manually construct the inner list item if you want to customize each item separately.
    ```
    """

    item_css: CssClasses = Field(default_factory=CssClasses, exclude=True)
    item_attributes: Attributes = Field(default_factory=Attributes, exclude=True)
    items: list[ListItem] = []

    @field_validator("items", mode="before")
    def add_li_if_missing(cls, items: list[str | BaseComponent]) -> list[ListItem]:
        return [
            ListItem(content=i) if not isinstance(i, ListItem) else i for i in items
        ]

    @model_validator(mode="after")
    def add_item_css_and_attributes(self):
        for item in self.items:
            item.css.update(self.item_css)
            item.attrs.update(self.item_attributes)
        return self

    @model_serializer()
    def serialize_as_item_content(self):
        # NOTE: This is so that when serializing this to dict/json,
        #       it appears as if it were `List[inner]`
        return [item.content for item in self.items]


class UnorderedList(_ListComponent):
    __quikui_component_name__ = "ul"


class OrderedList(_ListComponent):
    __quikui_component_name__ = "ol"


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


class Label(_SingleContentComponent):
    @model_validator(mode="before")
    @classmethod
    def convert_str_label(cls, val: str | dict) -> dict:
        if isinstance(val, str):
            return dict(content=val)

        return val


class FormInput(BaseComponent):
    type: Literal[InputType]
    name: str
    value: str | None = None
    label: Label | None = None
    add_break: bool = False
    required: bool = True

    @model_validator(mode="after")
    def add_id_to_label(self):
        if not (id := self.attrs.root.get("id")):
            id = self.attrs.root["id"] = self.name

        if self.label:
            self.label.attrs.root["for"] = id

        return self

    @classmethod
    def from_model_field(cls, field_name: str, field_info: FieldInfo) -> "FormInput":
        form_attributes = field_info.json_schema_extra.get("form_attributes", {})
        return cls(name=field_name, **form_attributes)


class TextInput(FormInput):
    type: Literal[InputType] = InputType.TEXT


class EmailInput(FormInput):
    type: Literal[InputType] = InputType.EMAIL


class PasswordInput(FormInput):
    type: Literal[InputType] = InputType.PASSWORD


class InputOption(BaseModel):
    id: str
    value: str
    label: Label


class InputWithOptions(FormInput):
    options: list[InputOption] = []

    @classmethod
    def from_model_field(cls, field_name: str, field_info: FieldInfo) -> "FormInput":
        form_attributes = field_info.json_schema_extra.get("form_attributes", {})

        # NOTE: Override to allow adding options directly from enum field annotation
        if "options" not in form_attributes and issubclass(field_info.annotation, Enum):
            form_attributes["options"] = [
                InputOption(
                    id=option.name,
                    value=option.value,
                    label=Label(attrs={"for": option.name}, content=option.value),
                )
                for option in field_info.annotation
            ]

        return cls(name=field_name, **form_attributes)
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


class Form(_MultiItemComponent):
    pass


class FormModel(BaseModel):
    """
    Model mix-in class that can produce a renderable form output.

    It is expected that you add the field metadata `form_type=Type[FormInput]`, and optionally
    you can include `field_attributes=dict(...)` to override the attributes of the generated
    FormInput class instance.

    ```note
    Does not subclass BaseComponent, you are meant to use `FormModel.create_form(...)` to produce
    `Form`, which is a `BaseComponent` object renderable to html
    ```
    """

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
    def create_form_items(cls, add_reset: bool = False) -> Iterator[BaseComponent]:
        """
        The sequence of form items that make up `Form.items` that is generated using
        `FormModel.create_form`

        You can override this method in your class to create a different layout pattern for your
        form. The default output yields:

            FormInput, Break, FormInput, Break, ..., Break, [ResetForm], SubmitForm
        """
        for field_name in cls.model_fields:
            yield cls.create_form_input(field_name)
            yield Break()

        if add_reset:
            yield ResetForm(name="reset")

        yield SubmitForm(name="submit")

    @classmethod
    def create_form(
        cls,
        add_reset: bool = False,
        css: List[str] = None,
        form_attrs: Dict[str, Any] = None,
        **attrs,
    ) -> Form:
        """
        Generate a `Form` component model which can be dumped to html
        """
        if form_attrs:
            attrs.update(form_attrs)

        return Form(
            css=css or [],
            attrs=attrs,
            items=list(cls.create_form_items(add_reset=add_reset)),
        )


__all__ = [
    BaseComponent.__name__,
    Heading.__name__,
    Paragraph.__name__,
    Break.__name__,
    Anchor.__name__,
    Button.__name__,
    Div.__name__,
    Span.__name__,
    ListItem.__name__,
    UnorderedList.__name__,
    OrderedList.__name__,
    Form.__name__,
    Label.__name__,
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
