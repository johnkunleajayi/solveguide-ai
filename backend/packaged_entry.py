"""Frozen Windows backend; existing development entry point remains unchanged."""

import argparse
import multiprocessing

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="SolveGuide localhost backend")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--managed", action="store_true", help="Private desktop-owned bootstrap")
    parser.add_argument("--personal-desktop", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.personal_desktop and not args.managed:
        parser.error("--personal-desktop requires managed startup")
    if args.managed:
        from app.managed_runtime import serve

        serve(personal_desktop=args.personal_desktop)
        return
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=args.port,
        access_log=False,
        loop="app.runtime:event_loop",
        http="h11",
        ws="none",
    )


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
