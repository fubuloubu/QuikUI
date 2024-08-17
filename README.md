# Overview

QuikUI is a library for contextual server-side rendering of Pydantic models into HTML components,
using Jinja2 for template-based rendering, and designed to work seamlessly with FastAPI-based apps.
One of the main benefits of QuikUI is that it allows you to create completely custom HTML for your
models just by subclassing `quikui.BaseComponent` in your model's class heirarchy, allowing you
to easily integrate HTML rendering into your existing FastAPI applications by just adding the
`quikui.render_component` decorator. Further, this rendering is contextual using a heuristic on
FastAPI requests, such that if a web browser makes a request to a supported endpoint in your app,
the app will respond with rendered html instead of converting your model to JSON in response.

## Installation

To install QuikUI, use `pip` or your favorite package installation tool:

```sh
$ pip install quikui
```

## Example

We have example in this repository that you can run via:

```sh
uvicorn example:app
```

## Usage

It is recommended that you subclass `quikui.BaseComponent` in a base class used by your heirarchy,
so that you can configure your own template directory:

```py
import quikui as qk


class Component(qk.BaseComponent):
    quikui_template_package_name = "your_package_name"
    # a folder called `templates/` under this package should contain your html templates


# Now you can subclass `Component` to enable rendering of your models.
```

Models are rendered according to their class name, so if you have a class like:

```py
class MyModel(Component, ...):
    a_field: str = Field(...)  # Works with any Pydantic Model type
    ...
```

Then it is expected to have a file under your package's template directory named `MyModel.html`:

```html
{# This is a Jinj2 template #}
<{{ __quikui_component_name__ }} class="{{ quikui_css_classes }}" {{ quikui_extra_attributes }}>
  {{ a_field }}
...
```

The template can use any named field of your model (the type is not converted, so handle
accordingly), or it can the QuikUI-provided fields `__quikui_component_name__` (the name of the model e.g.
`MyModel`), `quikui_css_classes` (which is the set of CSS classes that should be added),
and `quikui_extra_attributes` (which is a rendered "safe" string of html attributes in `k="v"` format, including the `class` attribute).

Additionally, there are two extra fields that are injected into your model when subclassing (which
are hidden from your model export via `model_dump` and `model_dump_json`) that you should use to
customize your objects: `attrs=dict(...)` (a mapping of html5-compatible string attribute names to string or bool values) and `css=set(...)` (a set of string css class names to concatenate together).

## Contributing

Open an [issue](https://github.com/fubuloubu/QuikUI/issues).
