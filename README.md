# QuikUI

> **Contextual server-side rendering of Pydantic models into HTML components**

QuikUI is a library designed for seamless integration of Pydantic models with HTML rendering using Jinja2 templates.
It's built specifically for modern web applications using FastAPI and HTMX, enabling powerful server-side rendering with fragment updates.

## Key Features

- **🎯 Zero Boilerplate**: Subclass `BaseComponent` and your Pydantic models automatically render to HTML
- **🔄 HTMX Native**: Built-in support for fragment rendering with template variants
- **📊 SQLModel Compatible**: Works seamlessly with SQLModel for ORM + rendering in one model
- **🎨 Template Variants**: Multiple template views per model (e.g., `Task.html`, `Task.table.html`, `Task.form.html`)
- **🔒 Safe by Default**: Automatic HTML escaping through Jinja2's autoescape
- **📡 SSE Streaming**: Built-in support for Server-Sent Events streaming
- **🎭 Smart Detection**: Automatic HTML vs JSON response based on request headers
- **⚠️ HTMX Error Handling**: Automatic error handling with native HTMX retargeting for validation errors and exceptions

## Installation

```bash
pip install quikui
```

## Quick Start

### 1. Define Your Models

Combine `BaseComponent` with your Pydantic models:

```python
import quikui as qk
from pydantic import Field

class Component(qk.BaseComponent):
    """Base class for all your renderable models"""
    quikui_template_package_name = "myapp"

class Task(Component):
    id: int
    title: str
    description: str = ""
    status: str = "todo"

# For SQLModel integration (in production):
# from sqlmodel import SQLModel
# class Task(Component, SQLModel, table=True):
#     # Your model definition
```

### 2. Create Templates

Create `myapp/templates/Task.html`:

```html
<div class="task">
  <h3>{{ title }}</h3>
  <p>{{ description }}</p>
  <span class="status">{{ status }}</span>
</div>
```

Create variant templates for different contexts like `Task.table.html`:

```html
<tr>
  <td>{{ title }}</td>
  <td>{{ description }}</td>
  <td>{{ status }}</td>
</tr>
```

### 3. Use in FastAPI Routes

```python
from fastapi import FastAPI
import quikui as qk

app = FastAPI()

# Register QuikUI filters for template variants
from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="myapp/templates")
qk.register_filters(templates.env)

@app.get("/tasks/{task_id}")
@qk.render_component()
def get_task(task_id: int) -> Task:
    task = session.get(Task, task_id)
    # Returns HTML when browser requests it
    # Returns JSON when API client requests it
    return task
```

## Core Concepts

### Template Discovery

QuikUI automatically finds templates based on your model's class name:

- `Task` → `Task.html` (default view)
- `Task` + `template_variant="table"` → `Task.table.html`
- `Task` + `template_variant="form"` → `Task.form.html`

Templates are searched in the package specified by `quikui_template_package_name` under the `templates/` directory.

### HTMX Fragment Rendering

Use the `Qk-Variant` header to specify which template variant to render:

```html
<!-- Create form that returns a table row -->
<form
  hx-post="/api/tasks"
  hx-target="#tasks-tbody"
  hx-swap="afterbegin"
  hx-headers='{"Qk-Variant": "table"}'
>
  <input name="title" required />
  <button type="submit">Create</button>
</form>

<!-- Table that displays tasks -->
<tbody id="tasks-tbody">
  {% for task in tasks %} {{ task|variant("table") }} {% endfor %}
</tbody>
```

The `|variant("table")` filter renders each task using `Task.table.html`.

#### DELETE Requests with HTMX

QuikUI automatically handles DELETE operations for both REST and HTMX clients:

```python
@app.delete("/api/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
@qk.render_component()
def delete_task(task_id: int):
    del tasks_db[task_id]
    # No return needed - None is implicit
```

**Behavior:**

- **JSON clients**: `204 No Content` (standard REST)
- **HTML/HTMX clients**: `200 OK` with empty string (enables element removal)

```html
<button
  hx-delete="/api/tasks/{{ id }}"
  hx-target="#task-{{ id }}"
  hx-swap="outerHTML"
>
  Delete
</button>
```

### Template Context

All model fields are automatically available in templates:

```python
class Task(Component):
    title: str
    status: TaskStatus  # Enum
    created_at: datetime
    tags: list[str]  # Complex types work too

    @computed_field
    @property
    def display_name(self) -> str:
        return f"Task: {self.title}"
```

In your template:

```html
<div>
  <h3>{{ title }}</h3>
  <span>{{ status.value }}</span>
  <time>{{ created_at.strftime('%Y-%m-%d') }}</time>
  <ul>
    {% for tag in tags %}
    <li>{{ tag }}</li>
    {% endfor %}
  </ul>
  <p>{{ display_name }}</p>
</div>
```

### SQLModel Relationships

SQLModel relationships are automatically included in the template context:

```python
class User(Component, table=True):
    id: int = Field(primary_key=True)
    name: str
    tasks: list["Task"] = Relationship(back_populates="user")

class Task(Component, table=True):
    id: int = Field(primary_key=True)
    title: str
    user_id: int = Field(foreign_key="users.id")
    user: User = Relationship(back_populates="tasks")
```

In `User.html`:

```html
<div class="user">
  <h2>{{ name }}</h2>
  <h3>Tasks:</h3>
  <ul>
    {% for task in tasks %} {{ task|variant("list") }} {% endfor %}
  </ul>
</div>
```

```{caution}
When using with SQLModel's lazy-loading relationship attributes, please use a sync db driver.
An async driver will not work and will cause async handling errors!
Jinja2 templating cannot work in an asynchronous context.
```

### Streaming with SSE

Stream components as Server-Sent Events:

```python
@app.get("/notifications")
@qk.render_component(streaming=True)
async def stream_notifications() -> AsyncIterator[Notification]:
    while True:
        await asyncio.sleep(1)
        yield Notification(message="Update", timestamp=datetime.now())
```

In your HTML:

```html
<div
  hx-ext="sse"
  sse-connect="/notifications"
  sse-swap="message"
  hx-swap="beforeend"
>
  <!-- Notifications appear here -->
</div>
```

### Global Template Context

Share context across all component renders:

```python
from quikui import set_context_provider

def get_global_context():
    return {
        "current_user": get_current_user(),
        "app_version": "1.0.0"
    }

set_context_provider(get_global_context)
```

Now all templates have access to `current_user` and `app_version`.

## Advanced Usage

### HTMX-Friendly Error Handling

QuikUI provides automatic error handling that works seamlessly with HTMX.
When errors occur (validation errors, 404s, etc.), QuikUI automatically detects whether the request is from HTMX or a JSON client and responds appropriately.

**Basic Setup (with built-in templates):**

```python
from fastapi import FastAPI
import quikui as qk

app = FastAPI()

# Use QuikUI's minimal built-in error templates
qk.setup_error_handlers(app)
```

**Custom Templates (to style your own):**

```python
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
import quikui as qk

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Use your own error templates
qk.setup_error_handlers(app, template_env=templates.env)
```

**Template Lookup Strategy:**

1. **TemplatedHTTPException** → Uses exception's own template with custom HTMX targeting
2. **HTTPException** → Tries `HTTPException.html` from your templates, then our basic one
3. **RequestValidationError** → Tries `RequestValidationError.html` from your templates, then our basic one
4. **Fallback** → If no templates found, simply falls back to FastAPI's own error strategy

**Creating Custom Error Templates (for basic FastAPI exceptions):**

Create `templates/HTTPException.html`:

```html
<div class="alert alert-danger">
  <strong>{{ status_text }}</strong>
  <p>{{ detail }}</p>
</div>
```

Create `templates/RequestValidationError.html`:

```html
<div class="alert alert-warning">
  <strong>Validation Error</strong>
  <ul>
    {% for error in errors %}
    <li><strong>{{ error.loc|join('.') }}:</strong> {{ error.msg }}</li>
    {% endfor %}
  </ul>
</div>
```

**HTMX Configuration (Required):**

By default, HTMX doesn't swap content on 4xx responses.
See https://htmx.org/docs/#response-handling for more information on how to set it up.

**In your HTML template:**

```html
<!-- Error container where errors will be displayed -->
<div id="error-container"></div>

<!-- Your form -->
<form hx-post="/api/tasks" hx-target="#task-list">
  <input name="title" required />
  <button type="submit">Create</button>
</form>
```

**Custom Exceptions with HTMX Targeting:**

For advanced use cases, create custom exceptions that control exactly where and how errors appear:

```python
class TaskInProgressError(qk.TemplatedHTTPException):
    """Custom exception with toast notification."""

    quikui_template_package_name = "myapp"
    error_container = "#toast-container"  # Where to display
    error_swap = "beforeend"              # How to insert
    template_variant = "toast"            # Which template variant

    def __init__(self, task_title: str):
        super().__init__(
            status_code=409,
            detail=f"Cannot delete '{task_title}' while in progress"
        )
        self.task_title = task_title

# Then create templates/TaskInProgressError.toast.html
```

**How it works:**

- **HTML/HTMX requests**: Returns rendered templates with optional `HX-Retarget` and `HX-Reswap` headers
- **JSON requests**: Returns standard FastAPI JSON error responses
- **Handles all FastAPI errors**: HTTPException (404, 403, etc.), RequestValidationError (422), and TemplatedHTTPException

**Example with validation:**

```python
@app.post("/api/tasks")
@qk.render_component()
def create_task(
    title: str = Form(..., min_length=1, max_length=200),
    description: str = Form(""),
) -> Task:
    # Validation happens automatically
    # Errors use your RequestValidationError.html template for HTMX
    # JSON clients get standard 422 response
    return Task(title=title, description=description)
```

### Custom Template Package

Override where QuikUI looks for templates:

```python
class Component(qk.BaseComponent):
    quikui_template_package_name = "myapp"
    quikui_template_package_path = "templates"  # default
```

### HTML-Only Routes

Force routes to only accept HTML requests (useful for rendering full pages):

```python
@app.get("/dashboard")
@qk.render_component(html_only=True, template="dashboard.html", env=templates)
def dashboard():
    return {"tasks": get_tasks(), "stats": get_stats()}
```

### Manual Template Selection

Use templates with regular Pydantic models:

```python
@app.get("/report")
@qk.render_component(template="report.html", env=templates)
def generate_report() -> ReportModel:
    return ReportModel(data=get_report_data())
```

### Wrapper Components

Wrap list results in a container:

```python
@app.get("/tasks")
@qk.render_component(
    wrapper=lambda *items: {"tasks": items},
    template="tasks_list.html",
    env=templates
)
def list_tasks() -> list[Task]:
    return session.query(Task).all()
```

## Example Application

The `example/` directory contains a complete task management application demonstrating:

- ✅ CRUD operations with HTMX
- ✅ Template variants for different contexts
- ✅ Inline editing with Alpine.js
- ✅ Server-sent events for notifications
- ✅ Form validation with HTMX-friendly error handling
- ✅ Production-ready patterns

Run the example:

```bash
uvicorn example:app --reload
```

Then visit http://localhost:8000/tasks

Note: The example uses in-memory storage for simplicity.
In production, you would integrate with SQLModel or another ORM for database persistence.

## Why QuikUI?

**Before QuikUI:**

```python
@app.get("/tasks/{task_id}")
def get_task(task_id: int, request: Request):
    task = session.get(Task, task_id)
    if "text/html" in request.headers.get("accept", ""):
        return templates.TemplateResponse(
            "task.html",
            {"request": request, "task": task.model_dump()}
        )
    return task
```

**With QuikUI:**

```python
@app.get("/tasks/{task_id}")
@qk.render_component()
def get_task(task_id: int) -> Task:
    return session.get(Task, task_id)
```

QuikUI eliminates boilerplate while providing powerful features for modern HTMX-based applications.

## Security

QuikUI uses Jinja2's autoescape by default, protecting against XSS attacks.
However, you are responsible for:

- Properly escaping user content in custom templates
- Validating and sanitizing user input
- Following OWASP security guidelines

See: [HTMX Security Basics](https://htmx.org/essays/web-security-basics-with-htmx/)

## Requirements

- Python 3.10+
- FastAPI
- Pydantic 2.0+
- Jinja2

## Contributing

Issues and pull requests welcome at [github.com/fubuloubu/QuikUI](https://github.com/fubuloubu/QuikUI)

## License

MIT License - see LICENSE file for details
