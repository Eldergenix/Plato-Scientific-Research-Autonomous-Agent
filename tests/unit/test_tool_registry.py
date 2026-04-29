"""§5.4 tests — typed Tool registry, permission gates, and built-in registrations."""
from __future__ import annotations

import asyncio
import inspect

import pytest
from pydantic import BaseModel

import plato.tools as tools_pkg
from plato.tools import builtin as tools_builtin
from plato.tools.registry import (
    Tool,
    ToolMetadata,
    _REGISTRY,
    call,
    get,
    list_tools,
    register,
)


class _Echo(BaseModel):
    msg: str


def _make_tool(
    name: str,
    *,
    fn,
    permissions: set[str] | None = None,
    category: str = "generic",
) -> Tool:
    return Tool(
        metadata=ToolMetadata(
            name=name,
            description=f"test tool {name}",
            permissions=permissions or set(),
            category=category,
        ),
        input_schema=_Echo,
        output_schema=_Echo,
        fn=fn,
    )


@pytest.fixture(autouse=True)
def _isolate_registry():
    """Snapshot and restore the global tool registry around each test."""
    saved = dict(_REGISTRY)
    _REGISTRY.clear()
    # Re-register built-ins so tests that probe them have a clean baseline.
    _REGISTRY.update(saved)
    try:
        yield
    finally:
        _REGISTRY.clear()
        _REGISTRY.update(saved)


def test_register_and_get_round_trip():
    def _fn(p: _Echo) -> _Echo:
        return _Echo(msg=p.msg.upper())

    tool = _make_tool("upper", fn=_fn)
    register(tool)
    assert get("upper") is tool


def test_register_duplicate_without_overwrite_raises():
    tool = _make_tool("dup", fn=lambda p: p)
    register(tool)
    with pytest.raises(ValueError, match="already registered"):
        register(tool)


def test_register_duplicate_with_overwrite_replaces():
    first = _make_tool("rep", fn=lambda p: _Echo(msg="first"))
    second = _make_tool("rep", fn=lambda p: _Echo(msg="second"))
    register(first)
    register(second, overwrite=True)
    assert get("rep") is second


def test_get_missing_name_raises_key_error():
    with pytest.raises(KeyError, match="Unknown tool"):
        get("nope")


def test_list_tools_filters_by_category():
    register(_make_tool("r1", fn=lambda p: p, category="retrieval"))
    register(_make_tool("r2", fn=lambda p: p, category="retrieval"))
    register(_make_tool("v1", fn=lambda p: p, category="validation"))

    retrieval = list_tools(category="retrieval")
    validation = list_tools(category="validation")

    assert {"r1", "r2"}.issubset(retrieval)
    assert "v1" not in retrieval
    assert "v1" in validation
    assert "r1" not in validation
    # Filter result must be sorted.
    assert retrieval == sorted(retrieval)
    # No filter returns everything we just registered (plus pre-existing).
    every = list_tools()
    assert {"r1", "r2", "v1"}.issubset(every)


def test_call_blocks_when_permission_missing():
    tool = _make_tool(
        "needs_net",
        fn=lambda p: _Echo(msg="ok"),
        permissions={"network"},
    )
    register(tool)
    with pytest.raises(PermissionError, match="network"):
        call("needs_net", _Echo(msg="hi"), allowed_permissions={"llm"})


def test_call_succeeds_when_permissions_satisfied():
    tool = _make_tool(
        "needs_llm",
        fn=lambda p: _Echo(msg=p.msg + "!"),
        permissions={"llm"},
    )
    register(tool)
    out = call("needs_llm", _Echo(msg="hi"), allowed_permissions={"llm", "network"})
    assert out.msg == "hi!"


def test_call_no_permission_check_when_allowed_is_none():
    tool = _make_tool(
        "trusted",
        fn=lambda p: _Echo(msg="x"),
        permissions={"network", "llm"},
    )
    register(tool)
    # allowed_permissions=None disables the gate.
    out = call("trusted", _Echo(msg="y"))
    assert out.msg == "x"


def test_sync_tool_returns_value_directly():
    tool = _make_tool("sync_tool", fn=lambda p: _Echo(msg=p.msg + "_sync"))
    register(tool)

    result = call("sync_tool", _Echo(msg="hello"))

    assert isinstance(result, _Echo)
    assert result.msg == "hello_sync"


def test_async_tool_returns_a_coroutine_caller_awaits():
    async def _afn(p: _Echo) -> _Echo:
        return _Echo(msg=p.msg + "_async")

    register(_make_tool("async_tool", fn=_afn))

    result = call("async_tool", _Echo(msg="hi"))

    assert inspect.iscoroutine(result)
    awaited = asyncio.run(result)
    assert awaited.msg == "hi_async"


def test_call_revalidates_payload_against_input_schema():
    """A BaseModel of the wrong class with the right shape should be coerced."""

    class _OtherEcho(BaseModel):
        msg: str

    register(_make_tool("revalidate", fn=lambda p: _Echo(msg=p.msg + "!")))

    out = call("revalidate", _OtherEcho(msg="x"))

    assert isinstance(out, _Echo)
    assert out.msg == "x!"


# --- builtin registration --------------------------------------------------


def test_builtin_tools_registered_after_import():
    # Importing plato.tools or plato.tools.builtin must register both.
    names = set(list_tools())
    assert "verify_citation" in names
    assert "search_literature" in names


def test_builtin_categories_match_spec():
    assert get("verify_citation").metadata.category == "validation"
    assert get("search_literature").metadata.category == "retrieval"


def test_builtin_permissions_include_network():
    assert "network" in get("verify_citation").metadata.permissions
    assert "network" in get("search_literature").metadata.permissions


def test_public_api_exports_tool_registry_surface():
    # Smoke-test the package re-exports.
    assert tools_pkg.Tool is Tool
    assert tools_pkg.ToolMetadata is ToolMetadata
    assert tools_pkg.register is register
    assert tools_pkg.get is get
    assert tools_pkg.list_tools is list_tools
    assert tools_pkg.call is call
    assert tools_pkg.builtin is tools_builtin
