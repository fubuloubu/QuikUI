from collections.abc import Container
from functools import cache
from itertools import chain
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    pass

from jinja2 import Environment, PackageLoader, Template
from jinja2 import TemplateNotFound as Jinja2TemplateNotFound
from pydantic import BaseModel

from .exceptions import NoTemplateFound


def is_component(value: Any) -> bool:
    """Helper function to check if a value is a BaseComponent instance."""
    return isinstance(value, BaseComponent)


class BaseComponent(BaseModel):
    """
    A subclass of `pydantic.BaseModel` that supports serialization to "safe" HTML. Serialization
    to HTML is done by parsing a Jinja2 template (distributed with an associated package).
    It is assumed that you take great care to properly handle user-generated content by "escaping"
    (making it safe) in your templates.

    Example usage:
        ```python
        import quikui as qk
        from sqlmodel import SQLModel, Field

        class Component(qk.BaseComponent, SQLModel):
            quikui_template_package_name = "myapp"

        class User(Component, table=True):
            id: int = Field(primary_key=True)
            name: str
            email: str

        # Create a template at myapp/templates/User.html:
        # <div class="user">
        #   <h3>{{ name }}</h3>
        #   <p>{{ email }}</p>
        # </div>

        # Use with FastAPI:
        @app.get("/users/{user_id}")
        @qk.render_component()
        def get_user(user_id: int) -> User:
            return session.get(User, user_id)
        ```

    ```{warning}
    The way this library is designed does its best to maintain the property of always auto-escaping
    user-driven content. However, it is possible to configure your own components using this
    library to ignore that invariant. Either way, as a developer it is your job to ensure safety of
    the environment you are creating in your user's browser. For more information, check out:
    https://htmx.org/essays/web-security-basics-with-htmx/#always-use-an-auto-escaping-template-engine
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
                ``MyClass.list.html`` if ``template_variant="list"``.
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
                ``MyClass.list.html`` for rendering in a list context, or ``MyClass.table.html``
                for rendering as a table row. Defaults to finding normal ``MyClass.html`` templates.
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

        # Get all fields from model_fields and model_computed_fields
        include_items: list[str] = []
        if include and hasattr(include, "__iter__"):
            include_items = list(include)  # type: ignore[arg-type]

        cls = self.__class__
        model_field_names = set(
            chain(
                cls.model_fields.keys(),
                cls.model_computed_fields.keys(),
                include_items,
            )
        )

        # Also include any public attributes that exist but aren't in model_fields
        # (e.g., SQLModel relationships which may be descriptors, not in __dict__)
        # NOTE: We use object.__getattribute__(self, '__dict__') to directly access the
        # instance dictionary. This bypasses Pydantic's __getattribute__ hook, avoiding
        # deprecated warnings, and automatically skips all class-level attributes
        # (ClassVars, methods, etc.) since they aren't in the instance __dict__.
        instance_dict = object.__getattribute__(self, "__dict__")

        # First, add attributes from instance __dict__ (skips class-level attributes)
        for attr in instance_dict:
            if (
                not attr.startswith("_")
                and attr not in model_field_names
                and attr not in exclude
            ):
                val = instance_dict[attr]
                if not callable(val):
                    model_field_names.add(attr)

        # Build dict with properties in original form, not serialized
        model_dict = {}
        for f in model_field_names:
            if f not in exclude:
                if f in instance_dict:
                    model_dict[f] = instance_dict[f]
                elif f in cls.model_fields or f in cls.model_computed_fields:
                    # Use object.__getattribute__ to get computed fields/properties
                    model_dict[f] = object.__getattribute__(self, f)
                else:
                    # May be a descriptor (e.g., SQLModel relationship)
                    try:
                        model_dict[f] = object.__getattribute__(self, f)
                    except AttributeError:
                        pass

        model_dict["__quikui_component_name__"] = (
            self.__quikui_component_name__ or self.__class__.__name__
        )

        # NOTE: Feed the rest of the kwargs to this function directly to the template rendering
        model_dict.update(kwargs)

        # Get global context from provider and merge it in
        # Global context is added first so component data takes precedence
        from .jinja import get_template_context

        global_context = get_template_context()
        context = {**global_context, **model_dict, **(render_context or {})}

        return self.quikui_template(template_variant=template_variant).render(**context)

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
