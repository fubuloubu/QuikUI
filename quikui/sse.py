from collections.abc import AsyncGenerator, AsyncIterator, Generator, Iterator
from typing import cast


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
        if self.event and self.retry:
            return f"event: {self.event}\ndata: {item}\nretry: {self.retry}\n\n"
        elif self.event:
            return f"event: {self.event}\ndata: {item}\n\n"
        elif self.retry:
            return f"data: {item}\nretry: {self.retry}\n\n"
        else:
            return f"data: {item}\n\n"

    async def __anext__(self) -> str:
        if isinstance(self.items, AsyncGenerator):
            item = cast(str, await anext(self.items))
            return self.format_item(item)

        item = cast(str, next(self.items))
        return self.format_item(item)
