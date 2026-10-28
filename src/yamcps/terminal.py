"""Styled terminal tables and escaped tab-separated redirected listings."""

import os
import sys
from collections.abc import Sequence
from typing import TextIO

from rich.console import Console
from rich.table import Table
from rich.text import Text


def console(stream: TextIO) -> Console:
    """Create a console that respects TTY detection and NO_COLOR.

    Args:
        stream: Explicit destination, including redirected test streams.

    Returns:
        Console with literal text, no automatic markup or highlighting.
    """
    return Console(
        file=stream,
        markup=False,
        highlight=False,
        force_terminal=stream.isatty(),
        color_system=None if "NO_COLOR" in os.environ else "auto",
    )


def field_header(label: str, description: str, *, default: str | None = None) -> None:
    """Present field metadata on stderr without any secret values.

    Args:
        label: Connector and field identifier.
        description: Human-readable declaration.
        default: Nonsecret default; None denotes a required field.
    """
    output = console(sys.stderr)
    output.print(Text(label, style="bold cyan"), Text(description))
    output.print(
        Text("Default: ", style="dim") + Text(repr(default) if default is not None else "required")
    )


def listing(
    headers: Sequence[str], rows: Sequence[Sequence[str]], *, plain_headers: bool = True
) -> None:
    """Render literal cells as a styled table on a terminal, TSV otherwise.

    Args:
        headers: Column headings.
        rows: Already selected display data; never pass secret values.
        plain_headers: Include a header in redirected TSV, unless preserving legacy output.
    """
    output = console(sys.stdout)
    if not output.is_terminal:
        if plain_headers:
            print("\t".join(headers))
        for row in rows:
            print(
                "\t".join(
                    cell.replace("\x1b", "\\x1b")
                    .replace("\r", "\\r")
                    .replace("\n", "\\n")
                    .replace("\t", "\\t")
                    for cell in row
                )
            )
        return
    table = Table(header_style="bold cyan")
    for index, header in enumerate(headers):
        table.add_column(header, style="cyan" if index == 0 else None, overflow="fold")
    for row in rows:
        table.add_row(*(Text(cell) for cell in row))
    output.print(table)
