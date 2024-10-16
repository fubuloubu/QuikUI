import random
from enum import Enum

import quikui as qk
from fastapi import Depends, FastAPI, Form, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

app = FastAPI()

# You can use your existing the templates the same
templates = Jinja2Templates(directory="example/templates")


# NOTE: It is recommended to exclude `html_only=True` routes from the schema
@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
# In fact, `template=` is a nice way to render pages directly without needing a custom Component
@qk.render_component(html_only=True, template="CustomPage.html", env=templates)
async def index():
    # NOTE: When using `template=`, you can just directly return a dict or BaseModel
    return dict(
        title="Basic Demo App",
        content=[
            qk.Div(
                qk.Heading("Basic Component Demo"),
                qk.Paragraph("This is a paragraph element."),
                qk.Div(
                    qk.Paragraph("This is a paragraph inside a div."),
                    qk.Paragraph("This is another paragraph inside a div."),
                    qk.Paragraph(
                        content=qk.Span(
                            "This is a span ",
                            qk.Anchor(
                                "with a link",
                                route="https://google.com",
                                # You can add extra html attributes via kwargs
                                target="_blank",  # NOTE: Open link in a new tab
                            ),
                            " to something inside that same div.",
                        )
                    ),
                    # Can add custom CSS classes to any component via `css=...`
                    css="my-3",
                ),
                qk.Paragraph(
                    qk.Span(
                        "This is another span with a link",
                        qk.Anchor(
                            " to another page",
                            route="/another-page",
                        ),
                        ", outside the div.",
                    ),
                ),
            )
        ],
    )


@app.get("/another-page")
# NOTE: You can supply a template directly, but be aware it will not automatically update
#       (Try modifying `CustomPage.html` and refreshing both this page and the previous)
@qk.render_component(html_only=True, template=templates.get_template("CustomPage.html"))
def another_page():
    return dict(
        title="A page with dynamic content",
        content=[
            qk.Heading("Using HTMX"),
            qk.Paragraph(
                "This button uses HTMX to dynamically fetch content"
                " from the server using a GET request."
            ),
            qk.Button(
                "Get Dynamic Content",
                # can also add extra attributes via `attrs=dict(...)` kwarg
                # NOTE: This is useful for when attrs have `-` in them, or are protected keywords
                attrs={"hx-get": "/dynamic", "type": "button", "hx-swap": "outerHTML"},
            ),
            qk.Button(
                "Get Form",
                attrs={"hx-get": "/form", "type": "button", "hx-swap": "outerHTML"},
            ),
        ],
    )


# NOTE: The components used do not have to be so fine-grained,
class CustomComponent(qk.BaseComponent):
    """To make a renderable component, just subclass BaseComponent"""

    # NOTE: If you override `quikui_template_package_name` class variable with your own
    #       package or app, and that contains a `/templates` folder that has a template
    #       with the name of this class and the `.html` extension, then it will "auto-render"
    quikui_template_package_name = "example"

    # You can add whatever fields you'd like to your model
    text: str = "Some random gibberish!"


@app.get("/dynamic")
@qk.render_component()  # NOTE: Allows both w/ html and json response modes when `html_only=False`
def dynamic_content():
    return [
        CustomComponent(text=random.choice(["Select", "Dynamic", "Content"]))
        for _ in range(random.randint(1, 10))
    ]


class CarTypes(Enum):
    NONE_SELECTED = "Select a Car"
    FIAT = "Fiat"
    DODGE = "Dodge"


# NOTE: This is not a component!
class CustomForm(qk.FormModel):
    username: str = Field(
        form_type=qk.TextInput,
        form_attributes=dict(label="Username:", add_break=True),
    )
    email: str = Field(
        form_type=qk.EmailInput,
        form_attributes=dict(label="Email:", add_break=True),
    )
    password: str = Field(
        form_type=qk.PasswordInput,
        form_attributes=dict(label="Password:", add_break=True),
    )
    save_password: bool = Field(
        form_type=qk.CheckboxInput,
        form_attributes=dict(label="Save Password?"),
    )
    car_choice: CarTypes = Field(
        form_type=qk.RadioInput,
        form_attributes=dict(label="First Choice:"),
    )
    backup_choice: CarTypes = Field(
        form_type=qk.SelectionInput,
        form_attributes=dict(
            label="Second Choice:",
            selected=CarTypes.NONE_SELECTED,
            disabled={CarTypes.NONE_SELECTED},
        ),
    )

    # NOTE: Override `.create_form_items()` with custom form item generator if desired


@app.get("/form")
@qk.render_component(html_only=True)  # NOTE: Only need this page to fetch the form
def form_page():
    return CustomForm.create_form(
        id="a-form", form_attrs={"hx-post": "/completed-form"}
    )


@app.post("/completed-form")
@qk.render_component(
    # You can give a "wrapper" component to use for wrapping an iterable result in html render mode
    wrapper=qk.UnorderedList,  # NOTE: By default uses `qk.Div`
    # NOTE: Can add additional keyword arguments to initializing `wrapper`
    wrapper_kwargs=dict(
        item_css={"my-5"},
        item_attributes=dict(something="else"),
    ),
)
async def receive_form(form: CustomForm = Depends(CustomForm.as_form)):
    # NOTE: The `form_handler` dependency will handle parsing and unflattening native HTML Forms
    return [f"{field}: {value}" for field, value in form.model_dump().items()]
