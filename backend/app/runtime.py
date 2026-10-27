"""Explicit loop factory: Psycopg async requires selectors on Windows."""

import asyncio
import sys


def event_loop():
    return asyncio.SelectorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app", host="127.0.0.1", port=8000, access_log=False, loop="app.runtime:event_loop"
    )
