import pytest
from jinja2 import DictLoader

import quikui as qk


@pytest.fixture
def loader():
    templates = {
        "Widget.html": "<div>{{ name }}: {{ count }}</div>",
        "Widget.card.html": '<div class="card">{{ name }}</div>',
    }
    return DictLoader(templates)


@pytest.fixture
def widget_class(loader):
    class Widget(qk.BaseComponent):
        name: str
        count: int

        @classmethod
        def quikui_environment(cls):
            env = super().quikui_environment()
            env.loader = loader
            return env

    return Widget


def test_variant_filter_registered(widget_class):
    env = widget_class.quikui_environment()
    assert "variant" in env.filters


def test_variant_filter_renders_component(widget_class):
    widget = widget_class(name="Test", count=1)
    env = widget_class.quikui_environment()
    template = env.from_string("{{ widget|variant('card') }}")
    result = template.render(widget=widget)
    assert '<div class="card">Test</div>' in result


def test_global_context_provider(widget_class):
    def get_context():
        return {"app_version": "1.0"}

    qk.set_context_provider(get_context)

    widget = widget_class(name="Test", count=5)
    html = widget.model_dump_html(render_context={})

    qk.set_context_provider(None)

    assert "<div>Test: 5</div>" in html
