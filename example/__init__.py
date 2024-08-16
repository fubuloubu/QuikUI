from fastapi import FastAPI, Request, Form, Depends
from enum import Enum
import quikui as qc
from pydantic import BaseModel, Field


app = FastAPI()


class CustomPage(qc.BaseComponent):
    html_template_package = "example"

    title: str
    content: list[qc.BaseComponent]


@app.get("/")
@app.get("/index.html")
@qc.render_component(html_only=True)
async def index():
    return CustomPage(
        title="Basic Demo App",
        content=[
            qc.Div(
                qc.Heading("Basic Component Demo"),
                qc.Paragraph("This is a paragraph element."),
                qc.Div(
                    qc.Paragraph("This is a paragraph inside a div."),
                    qc.Paragraph("This is another paragraph inside a div."),
                    qc.Paragraph(
                        content=qc.Span(
                            "This is a span ",
                            qc.Anchor(
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
                qc.Paragraph(
                    qc.Span(
                        "This is another span with a link",
                        qc.Anchor(
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
@qc.render_component(html_only=True)
def another_page():
    return CustomPage(
        title="A page with dynamic content",
        content=[
            qc.Heading("Using HTMX"),
            qc.Paragraph(
                "This button uses HTMX to dynamically fetch content"
                " from the server using a GET request."
            ),
            qc.Button(
                "Get Dynamic Content",
                # can also add extra attributes via `attrs=dict(...)` kwarg
                # NOTE: This is useful for when attrs have `-` in them, or are protected keywords
                attrs={"hx-get": "/dynamic", "type": "button", "hx-swap": "outerHTML"},
            ),
            qc.Button(
                "Get Form",
                attrs={"hx-get": "/form", "type": "button", "hx-swap": "outerHTML"},
            ),
        ],
    )


# NOTE: The components used do not have to be so fine-grained,
class CustomComponent(qc.BaseComponent):
    """To make a renderable component, just subclass BaseComponent"""

    text: str = "Some random gibberish!"

    def model_dump_html(self) -> str:
        """...and implement this method"""
        # NOTE: You do not have to subclass a component from the library, simply use whatever
        #       components or templates you'd like to use to render your models
        return qc.Paragraph(content=self.text).model_dump_html()

    # NOTE: If you override `html_template_package` class variable with your own
    #       package or app, and that contains a `/templates` folder that has a template
    #       with the name of this class and the `.html` extension, then it will "auto-render"


@app.get("/dynamic")
@qc.render_component()  # NOTE: Allowed both w/ html and json response modes when `html_only=False`
def dynamic_content():
    return CustomComponent()


class CarTypes(Enum):
    NONE_SELECTED = "Select a Car"
    FIAT = "Fiat"
    DODGE = "Dodge"


class CustomForm(qc.FormModel):
    username: str = Field(
        form_type=qc.TextInput,
        form_attributes=dict(label="Username:", add_break=True),
    )
    email: str = Field(
        form_type=qc.EmailInput,
        form_attributes=dict(label="Email:", add_break=True),
    )
    password: str = Field(
        form_type=qc.PasswordInput,
        form_attributes=dict(label="Password:", add_break=True),
    )
    save_password: bool = Field(
        form_type=qc.CheckboxInput,
        form_attributes=dict(label="Save Password?"),
    )
    car_choice: CarTypes = Field(
        form_type=qc.RadioInput,
        form_attributes=dict(label="First Choice:"),
    )
    backup_choice: CarTypes = Field(
        form_type=qc.SelectionInput,
        form_attributes=dict(
            label="Second Choice:",
            selected=CarTypes.NONE_SELECTED,
            disabled={CarTypes.NONE_SELECTED},
        ),
    )

    # NOTE: Override `.create_form_items()` with custom form item generator if desired


@app.get("/form")
@qc.render_component(html_only=True)  # NOTE: Only need this page to fetch the form
def form_page():
    return CustomForm.create_form(
        id="a-form", form_attrs={"hx-post": "/completed-form"}
    )


@app.post("/completed-form")
@qc.render_component(html_only=True)
async def receive_form(form: CustomForm = Depends(qc.form_handler(CustomForm))):
    return qc.Div(
        items=[
            qc.Paragraph(content="Form Data:"),
            qc.UnorderedList(
                # NOTE: You can give each item a uniform set of css/extra attrs via this:
                item_css={"my-5"},
                item_attributes=dict(something="else"),
                items=[
                    qc.Paragraph(content=f"{field}: {value}")
                    for field, value in form.model_dump().items()
                ],
            ),
        ]
    )
