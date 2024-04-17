from fastapi import FastAPI, Request, Form, Depends
from enum import Enum
import quikui as qc
from pydantic import BaseModel, Field


app = FastAPI()


@app.get("/")
@app.get("/index.html")
@qc.render_component(is_page=True)
async def index():
    return qc.Page(
        title="Basic Demo App",
        content=[
            qc.Div(
                qc.Heading(content="Basic Component Demo"),
                qc.Paragraph(content="This is a paragraph element."),
                qc.Div(
                    qc.Paragraph(content="This is a paragraph inside a div."),
                    qc.Paragraph(content="This is another paragraph inside a div."),
                    qc.Paragraph(
                        content=qc.Span(
                            "This is a span",
                            qc.Anchor(
                                content="with a link",
                                route="https://google.com",
                                target=qc.TargetType.NEW_WINDOW,
                            ),
                            "to something inside that same div.",
                        )
                    ),
                ),
                qc.Paragraph(
                    content=qc.Span(
                        "This is another span",
                        qc.Anchor(
                            content="with a link",
                            route="/another-page",
                            # NOTE: `.target` defaults to same page
                        ),
                        "to another page, outside the div.",
                    )
                ),
            )
        ],
    )


@app.get("/another-page")
@qc.render_component(is_page=True)
def another_page():
    return qc.Page(
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
                route="/dynamic", content="Get Dynamic Content", verb=qc.RequestType.GET
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
@qc.render_component()
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
        add_break=True,
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
@qc.render_component(is_page=True)
def form_page():
    return qc.Page(
        title="A page with a form",
        content=[CustomForm.create_form(id="a-form", route="/completed-form")],
    )


@app.post("/completed-form")
@qc.render_component(is_page=True)
async def receive_form(form: CustomForm = Depends(qc.form_handler(CustomForm))):
    return qc.Page(
        title="Form Data",
        content=[
            qc.Heading(content="Form Data"),
            *(
                qc.Paragraph(content=f"{field}: {value}")
                for field, value in form.dict().items()
            ),
        ],
    )
