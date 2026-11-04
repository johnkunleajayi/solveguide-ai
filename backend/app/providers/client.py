"""Application-owned SDK transport; requests keep independent timeouts and zero retries."""

from contextlib import asynccontextmanager


class ClientPool:
    def __init__(self):
        self.client = None

    def borrow(self, factory, options):
        # Synchronous initialization cannot interleave on the application's event loop.
        if self.client is None:
            self.client = factory(**options)
        return self.client.with_options(timeout=options["timeout"])

    async def close(self):
        if self.client is not None:
            await self.client.close()
            self.client = None


@asynccontextmanager
async def lease(pool, factory, **options):
    if pool is None:
        # Standalone provider/test use still owns and closes its transport.
        async with factory(**options) as client:
            yield client
    else:
        yield pool.borrow(factory, options)
