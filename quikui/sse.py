from collections.abc import AsyncGenerator, AsyncIterator, Generator, Iterator


class EventStream(AsyncIterator[str]):
    def __init__(
        self,
        items: AsyncIterator[str] | Iterator[str],
        event: str | None = None,
        retry: int | None = None,
    ):
        if not isinstance(items, (AsyncGenerator, Generator)):
            raise ValueError(f"{type(items)} must be `aiter` or `iter`.")

        self.items = items
        self.event = event
        self.retry = retry

    def __aiter__(self) -> AsyncIterator[str]:
        return self

    def format_item(self, item: str) -> str:
        match self.event, self.retry:
            case None, None:
                return f"data: {item}\n\n"

            case str(event), None:
                return f"event: {event}\ndata: {item}\n\n"

            case None, int(retry):
                return f"data: {item}\nretry: {retry}\n\n"

            case str(event), int(retry):
                return f"event: {event}\ndata: {item}\nretry: {retry}\n\n"

    async def __anext__(self) -> str:
        if isinstance(self.items, AsyncGenerator):
            return self.format_item(await anext(self.items))

        return self.format_item(next(self.items))
