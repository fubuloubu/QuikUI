from functools import cache

import pytest
from jinja2 import DictLoader, Environment
from sqlalchemy.pool import StaticPool
from sqlmodel import Field, Relationship, Session, SQLModel, create_engine

import quikui as qk


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def env():
    templates = {
        "Person.html": "<div>{{ name }} ({{ email }})</div>",
        "Person.card.html": '<div class="card">{{ name }}</div>',
        "Item.html": "<div>{{ title }} - {{ owner.name }}</div>",
        "Item.list.html": "<li>{{ title }}</li>",
        "Account.html": "<div>{{ username }}</div>",
    }
    env = Environment(loader=DictLoader(templates))
    qk.register_filters(env)
    return env


def test_sqlmodel_basic_fields(session, env):
    class Person(qk.BaseComponent, SQLModel, table=True):
        id: int | None = Field(default=None, primary_key=True)
        name: str
        email: str

        @classmethod
        @cache
        def quikui_environment(cls) -> Environment:
            return env

    SQLModel.metadata.create_all(session.bind)

    person = Person(id=1, name="Alice", email="alice@example.com")
    session.add(person)
    session.commit()
    session.refresh(person)

    html = person.model_dump_html()

    assert "Alice" in html
    assert "alice@example.com" in html


def test_sqlmodel_relationships(session):
    env = Environment(
        loader=DictLoader(
            {
                "Owner.html": "<div>{{ name }}</div>",
                "Item.html": "<div>{{ title }} - {{ owner.name }}</div>",
            }
        )
    )
    qk.register_filters(env)

    class Owner(qk.BaseComponent, SQLModel, table=True):
        id: int | None = Field(default=None, primary_key=True)
        name: str

        items: list["Item"] = Relationship(back_populates="owner")

        @classmethod
        @cache
        def quikui_environment(cls) -> Environment:
            return env

    class Item(qk.BaseComponent, SQLModel, table=True):
        id: int | None = Field(default=None, primary_key=True)
        title: str
        owner_id: int | None = Field(default=None, foreign_key="owner.id")

        owner: Owner = Relationship(back_populates="items")

        @classmethod
        @cache
        def quikui_environment(cls) -> Environment:
            return env

    SQLModel.metadata.create_all(session.bind)

    owner = Owner(name="Bob")
    item = Item(title="Build feature", owner=owner)
    session.add_all([owner, item])
    session.commit()
    session.refresh(owner)
    session.refresh(item)

    assert "owner" in item.__dict__ or hasattr(item, "owner")
    html = item.model_dump_html()
    assert "Build feature" in html
    assert "Bob" in html


def test_sqlmodel_variant_rendering(session, env):
    class Account(qk.BaseComponent, SQLModel, table=True):
        id: int | None = Field(default=None, primary_key=True)
        username: str

        @classmethod
        @cache
        def quikui_environment(cls) -> Environment:
            return env

    SQLModel.metadata.create_all(session.bind)

    account = Account(username="testuser")
    session.add(account)
    session.commit()
    session.refresh(account)

    html = account.model_dump_html()
    assert "testuser" in html


def test_sqlmodel_computed_fields(session):
    from pydantic import computed_field

    env_local = Environment(
        loader=DictLoader(
            {
                "Profile.html": "<div>{{ full_name }}</div>",
            }
        )
    )
    qk.register_filters(env_local)

    class Profile(qk.BaseComponent, SQLModel, table=True):
        id: int | None = Field(default=None, primary_key=True)
        first_name: str
        last_name: str

        @computed_field
        @property
        def full_name(self) -> str:
            return f"{self.first_name} {self.last_name}"

        @classmethod
        @cache
        def quikui_environment(cls) -> Environment:
            return env_local

    SQLModel.metadata.create_all(session.bind)

    profile = Profile(first_name="John", last_name="Doe")
    session.add(profile)
    session.commit()
    session.refresh(profile)

    html = profile.model_dump_html()
    assert "John Doe" in html
