import pytest

from quikui.sse import EventStream


def test_event_stream_with_sync_generator():
    """Test EventStream with a synchronous generator."""

    def items():
        yield "item1"
        yield "item2"
        yield "item3"

    stream = EventStream(items())
    assert stream.items is not None


def test_event_stream_format_item_basic():
    """Test basic formatting without event or retry."""

    def items():
        yield "hello"

    stream = EventStream(items())
    formatted = stream.format_item("hello")
    assert formatted == "data: hello\n\n"


def test_event_stream_format_item_with_event():
    """Test formatting with event name."""

    def items():
        yield "hello"

    stream = EventStream(items(), event="message")
    formatted = stream.format_item("hello")
    assert formatted == "event: message\ndata: hello\n\n"


def test_event_stream_format_item_with_retry():
    """Test formatting with retry."""

    def items():
        yield "hello"

    stream = EventStream(items(), retry=5000)
    formatted = stream.format_item("hello")
    assert formatted == "data: hello\nretry: 5000\n\n"


def test_event_stream_format_item_with_event_and_retry():
    """Test formatting with both event and retry."""

    def items():
        yield "hello"

    stream = EventStream(items(), event="update", retry=3000)
    formatted = stream.format_item("hello")
    assert formatted == "event: update\ndata: hello\nretry: 3000\n\n"


@pytest.mark.asyncio
async def test_event_stream_anext_sync_generator():
    """Test __anext__ with synchronous generator."""

    def items():
        yield "first"
        yield "second"

    stream = EventStream(items())
    first = await stream.__anext__()
    assert first == "data: first\n\n"

    second = await stream.__anext__()
    assert second == "data: second\n\n"


@pytest.mark.asyncio
async def test_event_stream_anext_async_generator():
    """Test __anext__ with asynchronous generator."""

    async def items():
        yield "async1"
        yield "async2"

    stream = EventStream(items())
    first = await stream.__anext__()
    assert first == "data: async1\n\n"

    second = await stream.__anext__()
    assert second == "data: async2\n\n"


@pytest.mark.asyncio
async def test_event_stream_iteration_async():
    """Test full async iteration."""

    async def items():
        yield "one"
        yield "two"
        yield "three"

    stream = EventStream(items(), event="test")
    results = []
    async for item in stream:
        results.append(item)

    assert len(results) == 3
    assert results[0] == "event: test\ndata: one\n\n"
    assert results[1] == "event: test\ndata: two\n\n"
    assert results[2] == "event: test\ndata: three\n\n"


def test_event_stream_invalid_items():
    """Test that EventStream raises ValueError for invalid items."""

    # Not a generator
    with pytest.raises(ValueError, match="must be `aiter` or `iter`"):
        EventStream(["not", "a", "generator"])  # type: ignore[arg-type]

    # Also not a generator
    with pytest.raises(ValueError, match="must be `aiter` or `iter`"):
        EventStream("not a generator")  # type: ignore[arg-type]


def test_event_stream_aiter():
    """Test that __aiter__ returns self."""

    def items():
        yield "test"

    stream = EventStream(items())
    assert stream.__aiter__() is stream
