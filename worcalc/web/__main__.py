"""Run the worCalc LAN web server."""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve worCalc on the local network")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run("worcalc.web.app:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
