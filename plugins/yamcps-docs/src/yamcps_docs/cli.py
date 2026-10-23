"""Offline document ingestion command."""

import argparse
import json
import sys
from pathlib import Path

from yamcps_docs import configured_index
from yamcps_docs.ingest import ingest


def main() -> None:
    """Ingest a complete manifest snapshot independently of the MCP server."""
    parser = argparse.ArgumentParser(description="Local document corpus ingestion")
    subcommands = parser.add_subparsers(dest="command", required=True)
    command = subcommands.add_parser("ingest", help="Synchronize one complete corpus manifest")
    command.add_argument("manifest", type=Path)
    command.add_argument("--chunk-size", type=int, default=1200)
    command.add_argument("--config-file", type=Path)
    args = parser.parse_args()
    try:
        result = ingest(
            configured_index(args.config_file), args.manifest, chunk_size=args.chunk_size
        )
    except Exception:
        print(
            "Ingestion failed. Check manifest, source formats and index/model configuration.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    print(json.dumps(result))
