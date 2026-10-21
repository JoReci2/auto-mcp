"""hmcp command line; stdout is reserved for stdio MCP traffic."""

import argparse
import logging

from hmcp.connectors import ConnectorError, discover
from hmcp.server import create_server


def main() -> None:
    parser = argparse.ArgumentParser(prog="hmcp")
    commands = parser.add_subparsers(dest="command", required=True)
    connectors = commands.add_parser("connectors").add_subparsers(dest="action", required=True)
    connectors.add_parser("list")
    serve = commands.add_parser("serve")
    serve.add_argument("--connector", action="append", required=True)
    serve.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    try:
        if args.command == "connectors":
            for name, entry in sorted(discover().items()):
                print(f"{name}\t{entry.value}")
            return
        if not 1 <= args.port <= 65535:
            parser.error("--port must be between 1 and 65535")
        server = create_server(args.connector)
        if args.transport == "stdio":
            server.run(transport="stdio")
        else:
            server.run(transport="streamable-http", host="127.0.0.1", port=args.port)
    except ConnectorError as exc:
        parser.exit(2, f"hmcp: {exc}\n")
