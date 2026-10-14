"""A sanitizing boundary between the tool bodies and the MCP client.

Why this exists: anything that escapes a tool body is wrapped by FastMCP into
``ToolError(f"Error executing tool {name}: {exc}")`` and that string is sent
straight to the client (see `Tool.run` in the SDK). With the database down,
the very first thing a reviewer saw was therefore a raw `[WinError 1225]`
connection-refused message, rendered in the *host machine's* system language.

That single line leaked an OS-specific error code, the locale of the machine
the server happens to run on, and the fact that an unhandled exception
reached the wire -- while telling the reader nothing they could act on. The
fix is not to hide failures but to answer the only question the client can
use: what should I do now.

Two rules govern what passes through:

* `ValueError` is re-raised untouched. Every one of them in this project is
  hand-written, English, user-facing validation text ("servings must be
  between 1 and 12."), it is what a conversational client should read back to
  the user, and the test suite asserts on those exact strings. Pydantic's
  `ValidationError` is a `ValueError` subclass and rides along deliberately:
  it describes the caller's own payload, not the server's internals.
* Everything else is logged server-side with a full traceback and replaced
  with a short English message. The operator keeps the diagnostic detail; the
  client gets an instruction.
"""
from __future__ import annotations

import functools
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from mcp.server.fastmcp.exceptions import ToolError
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

ResultT = TypeVar("ResultT")

# The failure a reviewer hits first, and the one worth naming precisely: the
# server is fine, PostgreSQL simply is not running. The remedy is one command,
# so the message is the command.
DATABASE_UNAVAILABLE = (
    "Inventory database unavailable - start it with: docker compose up -d"
)

# Connection refused arrives as an OSError subclass, sometimes bare from the
# asyncpg driver and sometimes wrapped by SQLAlchemy, so both are treated as
# "the database is not reachable" rather than falling through to the generic
# message. Messages are plain ASCII on purpose: they are also written to logs
# that may land on a console using a legacy code page.
_DATABASE_FAILURES: tuple[type[BaseException], ...] = (SQLAlchemyError, OSError)


def sanitize_tool_errors(
    fallback_message: str,
) -> Callable[[Callable[..., Awaitable[ResultT]]], Callable[..., Awaitable[ResultT]]]:
    """Replace unexpected exceptions with `fallback_message` for the client.

    `fallback_message` is what the caller sees when the failure is not a
    recognised database outage, so each tool supplies text naming its own
    dependencies.

    The wrapper keeps `functools.wraps`, which matters more than it looks:
    FastMCP derives each tool's JSON Schema from `inspect.signature(fn,
    eval_str=True)`, and that follows `__wrapped__`. Without it every tool
    would advertise `(*args, **kwargs)` instead of its real arguments.
    """

    def decorator(
        fn: Callable[..., Awaitable[ResultT]],
    ) -> Callable[..., Awaitable[ResultT]]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> ResultT:
            try:
                return await fn(*args, **kwargs)
            except ValueError:
                # Deliberate user-facing validation text; see the module
                # docstring. Re-raised so FastMCP reports it verbatim.
                raise
            except _DATABASE_FAILURES:
                logger.exception(
                    "Tool %s could not reach the database", fn.__name__
                )
                # `from None` drops the chained cause so no repr of the
                # original exception can follow the message outward.
                raise ToolError(DATABASE_UNAVAILABLE) from None
            except Exception:
                logger.exception("Tool %s failed unexpectedly", fn.__name__)
                raise ToolError(fallback_message) from None

        return wrapper

    return decorator
