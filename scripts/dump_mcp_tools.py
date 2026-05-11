#!/usr/bin/env python3
"""Dump the MCP tool surface from tools/*.py.

This keeps README/GUIDE from becoming a second hand-maintained schema.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"
DEFAULT_OUTPUT = ROOT / "docs" / "tools.md"


@dataclass(frozen=True)
class ToolInfo:
    name: str
    module: str
    signature: str
    summary: str
    docstring: str


def _unparse(node: ast.AST | None) -> str:
    if node is None:
        return "Any"
    try:
        return ast.unparse(node)
    except Exception:
        return "Any"


def _is_mcp_tool(func: ast.FunctionDef) -> bool:
    for decorator in func.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if (
            isinstance(target, ast.Attribute)
            and target.attr == "tool"
            and isinstance(target.value, ast.Name)
            and target.value.id == "mcp"
        ):
            return True
    return False


def _format_arg(arg: ast.arg, default: ast.AST | None) -> str:
    text = arg.arg
    if arg.annotation is not None:
        text += f": {_unparse(arg.annotation)}"
    if default is not None:
        text += f" = {_unparse(default)}"
    return text


def _signature(func: ast.FunctionDef) -> str:
    args = list(func.args.args)
    defaults: list[ast.AST | None] = [None] * (len(args) - len(func.args.defaults))
    defaults += list(func.args.defaults)
    parts = [_format_arg(arg, default) for arg, default in zip(args, defaults)]

    if func.args.vararg:
        parts.append("*" + _format_arg(func.args.vararg, None))

    if func.args.kwonlyargs:
        if not func.args.vararg:
            parts.append("*")
        for arg, default in zip(func.args.kwonlyargs, func.args.kw_defaults):
            parts.append(_format_arg(arg, default))

    if func.args.kwarg:
        parts.append("**" + _format_arg(func.args.kwarg, None))

    returns = _unparse(func.returns) if func.returns is not None else "Any"
    return f"{func.name}({', '.join(parts)}) -> {returns}"


def _summary(docstring: str) -> str:
    lines = [line.strip() for line in docstring.splitlines()]
    first_paragraph: list[str] = []
    for line in lines:
        if not line:
            if first_paragraph:
                break
            continue
        first_paragraph.append(line)
    return " ".join(first_paragraph)


def collect_tools() -> list[ToolInfo]:
    tools: list[ToolInfo] = []
    for path in sorted(TOOLS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and _is_mcp_tool(node):
                docstring = ast.get_docstring(node) or ""
                tools.append(
                    ToolInfo(
                        name=node.name,
                        module=f"tools/{path.name}",
                        signature=_signature(node),
                        summary=_summary(docstring),
                        docstring=docstring,
                    )
                )
    return sorted(tools, key=lambda tool: tool.name)


def render_markdown(tools: list[ToolInfo]) -> str:
    lines = [
        "# MCP Tools",
        "",
        "Generated from `tools/*.py` by `scripts/dump_mcp_tools.py`.",
        "",
        "MCP server name: `ctf_solver`",
        "",
        "## Summary",
        "",
        "| Tool | Module | Signature | Description |",
        "| --- | --- | --- | --- |",
    ]
    for tool in tools:
        summary = tool.summary.replace("|", "\\|")
        signature = tool.signature.replace("|", "\\|")
        lines.append(f"| `{tool.name}` | `{tool.module}` | `{signature}` | {summary} |")

    lines += ["", "## Details", ""]
    for tool in tools:
        lines += [
            f"### `{tool.name}`",
            "",
            f"- Module: `{tool.module}`",
            f"- Signature: `{tool.signature}`",
        ]
        if tool.docstring:
            lines += ["- Docstring:", "", "```text", tool.docstring.strip(), "```"]
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        nargs="?",
        const=str(DEFAULT_OUTPUT),
        help="write markdown to this path (default: docs/tools.md)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if docs/tools.md does not match generated output",
    )
    args = parser.parse_args()

    tools = collect_tools()
    if not tools:
        print("No MCP tools found", file=sys.stderr)
        return 1

    markdown = render_markdown(tools)

    if args.check:
        if not DEFAULT_OUTPUT.exists():
            print(f"{DEFAULT_OUTPUT} does not exist", file=sys.stderr)
            return 1
        current = DEFAULT_OUTPUT.read_text(encoding="utf-8")
        if current != markdown:
            print("docs/tools.md is stale; run scripts/dump_mcp_tools.py --write", file=sys.stderr)
            return 1
        print(f"OK: docs/tools.md matches {len(tools)} tools")
        return 0

    if args.write:
        output = Path(args.write)
        if not output.is_absolute():
            output = ROOT / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown, encoding="utf-8")
        try:
            display_path = output.relative_to(ROOT)
        except ValueError:
            display_path = output
        print(f"Wrote {display_path} ({len(tools)} tools)")
        return 0

    print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
