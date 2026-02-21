# QuikUI Tests

Run the test suite:

```bash
pytest tests/
```

Run with verbose output:

```bash
pytest tests/ -v
```

Run specific test file:

```bash
pytest tests/test_core.py -v
```

## Test Coverage

- **test_core.py**: Core functionality including HTML/JSON mode detection, CRUD operations, DELETE request handling, and template variants
- **test_filters.py**: Jinja2 filter registration and variant rendering
- **test_sqlmodel.py**: SQLModel integration including basic fields, relationships, variant rendering, and computed fields
