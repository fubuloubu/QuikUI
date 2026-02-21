from functools import cache

import pytest
from jinja2 import DictLoader, Environment

import quikui as qk


@pytest.fixture
def env():
    templates = {
        "Widget.html": "<div>{{ name }}: {{ count }}</div>",
        "Widget.card.html": '<div class="card">{{ name }}</div>',
    }
    env = Environment(loader=DictLoader(templates))
    qk.register_filters(env)
    return env


@pytest.fixture
def widget_class(env):
    class Widget(qk.BaseComponent):
        name: str
        count: int

        @classmethod
        @cache
        def quikui_environment(cls) -> Environment:
            return env

    return Widget


def test_variant_filter_registered(env):
    assert "variant" in env.filters


def test_variant_filter_renders_component(env, widget_class):
    widget = widget_class(name="Test", count=1)
    template = env.from_string("{{ widget|variant('card') }}")
    result = template.render(widget=widget)
    assert '<div class="card">Test</div>' in result


def test_global_context_provider(env, widget_class):
    def get_context():
        return {"app_version": "1.0"}

    qk.set_context_provider(get_context)

    widget = widget_class(name="Test", count=5)
    html = widget.model_dump_html(render_context={})

    qk.set_context_provider(None)

    assert "<div>Test: 5</div>" in html
