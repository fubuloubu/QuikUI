import string
from collections.abc import Container
from enum import Enum
from functools import cache
from itertools import chain
from typing import (Annotated, Any, Callable, ClassVar, Dict, Iterator, List,
                    Literal, Self, Set)

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from jinja2 import Environment, PackageLoader, Template
from jinja2 import TemplateNotFound as Jinja2TemplateNotFound
from markupsafe import Markup
from pydantic import (BaseModel, ConfigDict, Field, RootModel, ValidationError,
                      field_validator, model_serializer, model_validator)
from pydantic.fields import FieldInfo

from .exceptions import NoTemplateFound
from .utils import unflatten

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

    @model_validator(mode="before")
    @classmethod
    def convert_to_set(cls, val):
        if not val:
            return set()

        elif isinstance(val, str):
            return set(val.split(" "))

        elif isinstance(val, list):
            return set(val)

        return val

    @model_validator(mode="after")
    def validate_markup_safe(self):
        assert all(
            set(item).issubset(VALID_ATTR_CHARS) for item in self.root
        ), "Not in spec"
        return self

    @model_serializer()
    def serialize_css_classes(self) -> str:
        return " ".join(sorted(self.root))


class Attributes(RootModel):
    root: Dict[str, str | bool] = {}

    def __getitem__(self, key):
        return self.root.__getitem__(key)

    def get(self, key):
        return self.root.get(key)

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
                # NOTE: Don't render non-"truthy" values e.g. `something=false`
                if v  # Relies on truthiness to render bools and strings correctly
            )
        )


class BaseComponent(BaseModel):
    """
    A subclass of `pydantic.BaseModel` that supports serialization to "safe" HTML. Serialization
    to HTML is either done by parsing a Jinja2 template (distributed with an associated package),
    or by explicitly overriding the `model_dump_html` function in a subclass. It is assumed that
    you take great care to properly handle user-generated content by "escaping" (making it safe).

    ```{warning}
    The way this library is designed does its best to maintain the property of always auto-escaping
    user-driven content. However, it is possible to configure your own components using this
    library to ignore that invariant. Either way, as a developer it is your job to ensure safety of
    the environment you are creating in your user's browser. For more information, check out:
    https://htmx.org/essays/web-security-basics-with-htmx/#always-use-an-auto-escaping-template-engine
    ```

    ```{note}
    Cannot use this model if you rely on special behavior with `ConfigDict(extras="allow")`, as this
    component overwrites the value of `__pydantic_extra__` with custom behavior for additonal attrs.
    ```
    """

    quikui_template_package_name: ClassVar[str] = "quikui"
    """The package that should be used to search for templates for components that do not
    override `model_dump_html`. If you want to define custom components using your own templates,
    override this in your base class and provide your package's name. Templates are stored in the
    `./{quikui_template_package_path}` directory as a package resource. Defaults to this package."""

    quikui_template_package_path: ClassVar[str] = "templates"
    """The directory inside this package that should be used to search for model templates to
    render. Defaults to `./templates`. Must be a package resource bundled with the package."""

    __quikui_component_name__: ClassVar[str | None] = None
    """To override the value of ``__quikui_component_name__`` when rendering the component."""

    __quikui_css_classes__: CssClasses
    """Add extra CSS classes to this component. Useful for integration with your design system."""

    __quikui_extra_attributes__: Attributes
    """Add extra attributes to this component. Exposed to template rendering."""

    # NOTE: Needed to fetch extra kwargs to models (will be discarded in `__init__`)
    __pydantic_extra__: dict[str, Any] = {}
    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def parse_css_and_attrs(self):
        if hasattr(self, "__quikui_css_classes__") and hasattr(
            self, "__quikui_extra_attributes__"
        ):
            return self

        self.__quikui_css_classes__ = (
            CssClasses(root=self.__pydantic_extra__.pop("css", set()))
            if self.__pydantic_extra__
            else CssClasses()
        )

        if self.__pydantic_extra__:
            attrs = self.__pydantic_extra__.pop("attrs", dict())
            attrs.update(self.__pydantic_extra__)
            self.__quikui_extra_attributes__ = Attributes(root=attrs)

        else:
            self.__quikui_extra_attributes__ = Attributes()

        self.__pydantic_extra__ = {}  # Remove extras

        return self

    @classmethod
    @cache
    def quikui_environment(cls) -> Environment:
        """
        The environment to search for templates for this class and all it's subclasses.

        Returns:
            :class:`~jinja2.Environment`:
                The environment to search for template(s) to render this class with.

        ```{note}
        This method is cached since environments will typically not change during runtime.
        ```
        """
        env = Environment(
            loader=PackageLoader(
                package_name=cls.quikui_template_package_name,
                package_path=cls.quikui_template_package_path,
            ),
            autoescape=True,
        )
        # NOTE: Add our special filters here
        env.filters.update({"is_component": is_component})
        return env

    @classmethod
    def quikui_template(cls, template_variant: str | None = None) -> Template:
        """
        The template that should be used to render this model.

        Args:
            template_variant (str | None): Template type (file extension prepend) to find.
                This allows the use of custom templates for different scenarios, such as
                ``MyClass.list.html`` if ``template_type="list"``.
                Defaults to finding templates by their classname e.g. ``MyClass.html``.

        Returns:
            :class:`~jinja2.Template`: The template to render this model with.

        Raises:
            :class:`~quikui.NoTemplateFound`: If no template was found while recursing.

        ```{note}
        This method is not cached so updates to templates do not require reloading.
        ```

        ```{note}
        This classmethod is useful in combination with the ``template_variant`` keyword argument on
        the :func:`~quikui.render_component` decorator function in order to directly render a
        component.
        ```
        """
        template_class = cls
        while issubclass(template_class, BaseComponent):
            env = template_class.quikui_environment()

            try:
                return env.get_template(
                    f"{template_class.__name__}.{template_variant}.html"
                    if template_variant
                    else f"{template_class.__name__}.html"
                )

            except Jinja2TemplateNotFound:
                # If no template is found, recurse up the class heirarchy through `.__base__`
                # NOTE: Potentially dangerous if multi-class heirarchy exists, only uses first base
                assert template_class.__base__  # NOTE: For mypy
                template_class = template_class.__base__

        # NOTE: If we get to BaseComponent, there was some error in user's environment
        raise NoTemplateFound(cls, template_variant)

    def model_dump_html(
        self,
        include: Container | None = None,
        exclude: Container | None = None,
        template_variant: str | None = None,
        render_context: dict | None = None,
        **kwargs: dict,
    ) -> str:
        """
        Render this model to "safe" HTML. This default implementation assumes that a template
        exists for this model in `Class.quikui_environment` that can be used to serialize this
        model by it's top-level fields, including computed fields and any other fields that should
        be included.

        Args:

            include: Fields to include that would otherwise be skipped.
            exclude: Fields that should be skipped which would otherwise be included.
            template_variant (str | None): Template type (file extension) to find.
                This allows the use of custom templates for different scenarios, such as
                ``MyClass.list.html``. Defaults to finding normal ``MyClass.html`` templates.
            render_context (dict | None): Extra context to pass to ``.quikui_template(...).render``
            **kwargs: Any other attributes you want to pass directly to Jinja2 template rendering.

        Returns:
            (str): The rendered "safe" HTML that FastAPI will insert directly into a Response for
                this model.

        ```{note}
        You can override this if you can directly return "safe" html without using a template.
        ```

        ```{warning}
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
            # NOTE: Ensure properties are in original form, not serialized
            (f, getattr(self, f))
            # NOTE: Ensure we get all public, computed, and any requested private fields...
            for f in chain(self.model_fields, self.model_computed_fields, include)
            #       ...but also allow skipping fields we don't need for template context.
            if f not in exclude
        )

        # NOTE: Because SQLModel doesn't run validators on DB load
        self.parse_css_and_attrs()

        if attrs := self.__quikui_extra_attributes__:
            model_dict["quikui_extra_attributes"] = attrs.model_dump()

        if css := self.__quikui_css_classes__:
            model_dict["quikui_css_classes"] = css.model_dump()

        model_dict["__quikui_component_name__"] = (
            self.__quikui_component_name__ or self.__class__.__name__
        )

        # NOTE: Feed the rest of the kwargs to this function directly to the template rendering
        model_dict.update(kwargs)

        return self.quikui_template(template_variant=template_variant).render(
            **model_dict,
            **(render_context or {}),
        )

    def __html__(self) -> str:
        """
        Serialize this model to "safe" HTML, using default settings for field include/exclude.
        This should not be overriden, except to modify how `model_dump_html` gets called by Jinja2.

        Returns:
            (str): The rendered "safe" HTML that FastAPI will insert directly into a Response for
                this model when using :func:`quikui.render_component`.

        ```{note}
        This allows `BaseComponent` models to automatically serialize themselves as HTML when used
        in a Jinga2 template. We can include private fields for the template engine this way.
        ```
        """
        return self.model_dump_html()


class Break(BaseComponent):
    def model_dump_html(self, **kwargs) -> str:
        return "<br>"


class Image(BaseComponent):
    source: str
    alt_text: str


class _SingleContentComponent(BaseComponent):
    content: str | BaseComponent

    @model_validator(mode="before")
    @classmethod
    def parse_content(cls, val) -> dict:
        if not isinstance(val, dict):
            return dict(content=val)

        return val

    def __init__(self, content: str | BaseComponent | None = None, **kwargs):
        # NOTE: Lets us do `cls(val)` instead of `cls(content=val)`
        if content:
            kwargs["content"] = content
        super().__init__(**kwargs)


class Heading(_SingleContentComponent):
    level: Annotated[int, Field(strict=True, ge=1, le=5, exclude=True)] = 1

    @property
    def __quikui_component_name__(self) -> str:
        return f"h{self.level}"


class Paragraph(_SingleContentComponent):
    __quikui_component_name__ = "p"


class Anchor(_SingleContentComponent):
    __quikui_component_name__ = "a"
    route: str


class Button(_SingleContentComponent):
    pass


class _MultiItemComponent(BaseComponent):
    items: list[str | BaseComponent] = []

    def __init__(self, *items, **kwargs):
        # NOTE: Let's us do `cls(*vals)` instead of `cls(items=vals)`
        if "items" not in kwargs:
            kwargs["items"] = list(items)

        elif len(items) > 0:
            raise ValueError(
                f"Cannot use `{self.__class__.__name__}(*items)` with `items=` kwarg."
            )

        super().__init__(**kwargs)


class Div(_MultiItemComponent):
    pass


class Span(_MultiItemComponent):
    pass


class ListItem(_SingleContentComponent):
    __quikui_component_name__ = "li"


class _ListComponent(_MultiItemComponent):
    """
    Component class that renders as a list component, with the inner content wrapped as `li`
    elements. Implemented in such as a way that you can get correct type hints on what it returns
    in the normal case where JSON is rendered, making it easy to use for both API and HTML modes.

    Usage example::

        >>> @app.get("/items")
        >>> @qk.render_component(wrapper=qk.UnorderedList)  # What it returns in HTML mode
        >>> def get_items() -> list[MyItem]:  # What it returns in JSON mode
        >>>     return session.exec(select(MyItem)).all()  # `MyItem` subclasses `BaseComponent`

    ```note
    You can add a common set of css classes or attributes to the inner list items by specifying
    ``item_css=set(...)`` and/or ``item_attributes=dict(...)`` to the class initialization. You
    can also manually construct the inner list item if you want to customize each item separately.
    ```
    """

    item_css: CssClasses | Callable[[int, ListItem], None] = Field(
        default_factory=CssClasses, exclude=True
    )
    item_attributes: Attributes | Callable[[int, ListItem], None] = Field(
        default_factory=Attributes, exclude=True
    )
    items: list[ListItem] = []

    @field_validator("items", mode="before")
    def add_li_if_missing(cls, items: list[str | BaseComponent]) -> list[ListItem]:
        return [
            ListItem(content=i) if not isinstance(i, ListItem) else i for i in items
        ]

    @model_validator(mode="after")
    def add_item_css_and_attributes(self):
        if isinstance(self.item_css, CssClasses):

            def apply_css_to_item(_: int, item: ListItem):
                item.__quikui_css_classes__.update(self.item_css)

        else:
            apply_css_to_item = self.item_css

        if isinstance(self.item_attributes, Attributes):

            def add_attributes_to_item(_: int, item: ListItem):
                item.__quikui_extra_attributes__.update(self.item_attributes)

        else:
            add_attributes_to_item = self.item_attributes

        for idx, item in enumerate(self.items):
            apply_css_to_item(idx, item)
            add_attributes_to_item(idx, item)

        return self


class UnorderedList(_ListComponent):
    __quikui_component_name__ = "ul"


class OrderedList(_ListComponent):
    __quikui_component_name__ = "ol"


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
        if not (id := self.__quikui_extra_attributes__.get("id")):
            id = self.__quikui_extra_attributes__["id"] = self.name

        if self.label:
            self.label.__quikui_extra_attributes__["for"] = id

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
            css=css,
            attrs=attrs,
            items=list(cls.create_form_items(add_reset=add_reset)),
        )

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
