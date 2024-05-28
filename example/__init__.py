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
                items=[
                    qc.Heading(content="Basic Component Demo"),
                    qc.Paragraph(content="This is a paragraph element."),
                    qc.Div(
                        css={"my-3"},  # Can add custom CSS classes to any component
                        items=[
                            qc.Paragraph(content="This is a paragraph inside a div."),
                            qc.Paragraph(
                                content="This is another paragraph inside a div."
                            ),
                            qc.Paragraph(
                                content=qc.Span(
                                    items=[
                                        "This is a span ",
                                        qc.Anchor(
                                            content="with a link",
                                            route="https://google.com",
                                            attrs=dict(target="_blank"),
                                        ),
                                        " to something inside that same div.",
                                    ]
                                )
                            ),
                        ],
                    ),
                    qc.Paragraph(
                        # can also add extra attributes
                        attrs=dict(something="blah"),
                        content=qc.Span(
                            items=[
                                "This is another span ",
                                qc.Anchor(
                                    content="with a link",
                                    route="/another-page",
                                    # NOTE: `.target` defaults to same page
                                ),
                                " to another page, outside the div.",
                            ]
                        ),
                    ),
                ]
            )
        ],
    )


@app.get("/another-page")
@qc.render_component(html_only=True)
def another_page():
    return CustomPage(
        title="A page with dynamic content",
        content=[
            qc.Heading(content="Using HTMX"),
            qc.Paragraph(
                content=(
                    "This button uses HTMX to dynamically fetch content"
                    " from the server using a GET request."
                )
            ),
            qc.Button(
                attrs={"hx-get": "/dynamic", "type": "button", "hx-swap": "outerHTML"},
                content="Get Dynamic Content",
            ),
            qc.Button(
                attrs={"hx-get": "/form", "type": "button", "hx-swap": "outerHTML"},
                content="Get Form",
            ),
        ],
    )


class CustomComponent(qc.BaseComponent):
    """To make a renderable component, just subclass this..."""

    text: str = "Some random gibberish!"

    def model_dump_html(self) -> str:
        """...and implement this method"""
        # NOTE: You do not have to subclass a component from the library,
        #       simply use whatever components you'd like to use to render
        return qc.Paragraph(content=self.text).model_dump_html()

    # NOTE: If you override `html_template_package` class variable with your own
    #       package or app, and that contains a `/templates` folder that has a template
    #       with the same name as this class, then it will "auto-render" using that template
    #       without having to override `model_dump_html`


@app.get("/dynamic")
@qc.render_component()  # NOTE: Allowed both w/ html and json response modes
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
                items=[
                    qc.Paragraph(content=f"{field}: {value}")
                    for field, value in form.model_dump().items()
                ],
            ),
        ]
    )
