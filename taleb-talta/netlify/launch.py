"""Loopback-only uvicorn launcher used by the Netlify Node adapter."""
from __future__ import annotations

import argparse
import asyncio
import json
import signal
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def serve(port: int, token: str):
    import uvicorn
    from app.main import app

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    sock.setblocking(False)
    actual = sock.getsockname()[1]
    config = uvicorn.Config(app, lifespan="on", loop="asyncio", http="h11",
                            access_log=False, server_header=False, date_header=False)
    server = uvicorn.Server(config)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda: setattr(server, "should_exit", True))
        except NotImplementedError:
            pass
    task = asyncio.create_task(server.serve(sockets=[sock]))
    while not server.started and not task.done():
        await asyncio.sleep(0.02)
    if task.done():
        await task
        raise RuntimeError("startup_failed")
    print("TT_READY " + json.dumps({"port": actual, "token": token}), flush=True)
    await task


async def initialize():
    from app.main import app
    async with app.router.lifespan_context(app):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--token", default="")
    parser.add_argument("--initialize", action="store_true")
    args = parser.parse_args()
    if args.initialize:
        asyncio.run(initialize())
    else:
        if not args.token:
            parser.error("--token is required")
        asyncio.run(serve(args.port, args.token))


if __name__ == "__main__":
    main()
