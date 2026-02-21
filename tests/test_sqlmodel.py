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


def test_sqlmodel_detached_instance_error():
    """Test that DetachedInstanceError provides helpful error message."""
    from sqlalchemy.orm.exc import DetachedInstanceError

    env = Environment(
        loader=DictLoader(
            {
                "Company.html": "<div>{{ name }}</div>",
                "Task.html": "<div>{{ title }} - {{ company.name }}</div>",
            }
        )
    )
    qk.register_filters(env)

    class Company(qk.BaseComponent, SQLModel, table=True):
        id: int | None = Field(default=None, primary_key=True)
        name: str
        tasks: list["Task"] = Relationship(back_populates="company")

        @classmethod
        @cache
        def quikui_environment(cls) -> Environment:
            return env

    class Task(qk.BaseComponent, SQLModel, table=True):
        id: int | None = Field(default=None, primary_key=True)
        title: str
        company_id: int | None = Field(default=None, foreign_key="company.id")
        company: Company = Relationship(back_populates="tasks")

        @classmethod
        @cache
        def quikui_environment(cls) -> Environment:
            return env

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    # Create data and get task_id
    with Session(engine) as session:
        company = Company(name="Bob")
        task = Task(title="Build feature", company=company)
        session.add_all([company, task])
        session.commit()
        task_id = task.id

    # Query without eager loading and close session
    with Session(engine) as session:
        task = session.get(Task, task_id)
        assert task is not None

    # Now session is closed - should raise DetachedInstanceError with helpful message
    with pytest.raises(DetachedInstanceError) as exc_info:
        task.model_dump_html()

    error_message = str(exc_info.value)
    assert "QuikUI hint" in error_message
    assert "relationship 'company'" in error_message
    assert "selectinload" in error_message
    assert "Task.company" in error_message


def test_sqlmodel_eager_loaded_relationships():
    """Test that eager-loaded relationships work even after session closes."""
    from sqlalchemy.orm import selectinload
    from sqlmodel import select

    env = Environment(
        loader=DictLoader(
            {
                "Author.html": "<div>{{ name }}</div>",
                "Book.html": "<div>{{ title }} - {{ author.name }}</div>",
            }
        )
    )
    qk.register_filters(env)

    class Author(qk.BaseComponent, SQLModel, table=True):
        id: int | None = Field(default=None, primary_key=True)
        name: str
        books: list["Book"] = Relationship(back_populates="author")

        @classmethod
        @cache
        def quikui_environment(cls) -> Environment:
            return env

    class Book(qk.BaseComponent, SQLModel, table=True):
        id: int | None = Field(default=None, primary_key=True)
        title: str
        author_id: int | None = Field(default=None, foreign_key="author.id")
        author: Author = Relationship(back_populates="books")

        @classmethod
        @cache
        def quikui_environment(cls) -> Environment:
            return env

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    # Create data and get book_id
    with Session(engine) as session:
        author = Author(name="Alice")
        book = Book(title="Important task", author=author)
        session.add_all([author, book])
        session.commit()
        book_id = book.id

    # Query WITH eager loading
    with Session(engine) as session:
        book = session.exec(
            select(Book).where(Book.id == book_id).options(selectinload(Book.author))  # type: ignore[arg-type]
        ).first()
        assert book is not None
        # Verify author is in __dict__ after eager loading
        assert "author" in book.__dict__

    # Session is closed, but should still work because relationship was eager-loaded
    html = book.model_dump_html()
    assert "Important task" in html
    assert "Alice" in html


def test_sqlmodel_relationship_in_instance_dict():
    """Test that relationships already in instance.__dict__ are included."""
    env = Environment(
        loader=DictLoader(
            {
                "Customer.html": "<div>{{ name }}</div>",
                "Order.html": "<div>{{ title }} - {{ customer.name }}</div>",
            }
        )
    )
    qk.register_filters(env)

    class Customer(qk.BaseComponent, SQLModel, table=True):
        id: int | None = Field(default=None, primary_key=True)
        name: str
        orders: list["Order"] = Relationship(back_populates="customer")

        @classmethod
        @cache
        def quikui_environment(cls) -> Environment:
            return env

    class Order(qk.BaseComponent, SQLModel, table=True):
        id: int | None = Field(default=None, primary_key=True)
        title: str
        customer_id: int | None = Field(default=None, foreign_key="customer.id")
        customer: Customer = Relationship(back_populates="orders")

        @classmethod
        @cache
        def quikui_environment(cls) -> Environment:
            return env

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        customer = Customer(name="Charlie")
        order = Order(title="Test order", customer=customer)
        session.add_all([customer, order])
        session.commit()
        session.refresh(order)

        # When we're still in session, relationship gets loaded into __dict__
        _ = order.customer  # Access to trigger load
        assert "customer" in order.__dict__

        html = order.model_dump_html()
        assert "Test order" in html
        assert "Charlie" in html
