"""Built-in MCP server exposing Plato's local scientific tool registry."""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from .builtin import (
    ExpansionHunterDenovoInput,
    GauchianCallingInput,
    GenomicsToolReportInput,
    IlluminaIcaRequestInput,
    ParagraphGenotypingInput,
    ScientificAnalysisInput,
    ScientificCapabilityReportInput,
    ZippyPipelineInput,
)
from .registry import Permission, call, get, is_enabled, list_tools


mcp = FastMCP(
    "Plato Tool Registry",
    instructions=(
        "Expose Plato's built-in scientific tools to MCP clients. "
        "Disabled tools are omitted or refused according to PLATO_DISABLED_TOOLS."
    ),
)


def _tool_payload(name: str) -> dict[str, Any]:
    tool = get(name)
    return {
        "name": tool.metadata.name,
        "description": tool.metadata.description,
        "category": tool.metadata.category,
        "permissions": sorted(tool.metadata.permissions),
        "enabled": is_enabled(name),
        "input_schema": tool.input_schema.model_json_schema(),
        "output_schema": tool.output_schema.model_json_schema(),
    }


@mcp.tool()
def list_plato_tools() -> list[dict[str, Any]]:
    """List enabled and disabled Plato tools with schemas and permissions."""
    return [_tool_payload(name) for name in list_tools()]


@mcp.tool()
def scientific_capability_report() -> dict[str, Any]:
    """Return Plato's deterministic scientific capability report."""
    result = call("scientific_capability_report", ScientificCapabilityReportInput())
    return result.model_dump(mode="json")


@mcp.tool()
def genomics_tool_report() -> dict[str, Any]:
    """Return Plato's optional Illumina genomics integration report."""
    result = call("genomics_tool_report", GenomicsToolReportInput())
    return result.model_dump(mode="json")


@mcp.tool()
def prepare_genomics_tool_run(tool_name: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Prepare an optional genomics tool run; execute only when payload.execute is true."""
    registry_name, schema, permissions = _genomics_tool_mapping(tool_name)
    result = call(
        registry_name,
        schema.model_validate(payload or {}),
        allowed_permissions=permissions,
    )
    return result.model_dump(mode="json")


@mcp.tool()
def run_scientific_analysis(
    operation: str,
    data: dict[str, Any] | None = None,
    output_dir: str | None = None,
    random_seed: int = 1729,
) -> dict[str, Any]:
    """Run a deterministic Plato scientific-analysis operation."""
    payload = ScientificAnalysisInput.model_validate(
        {
            "operation": operation,
            "data": data or {},
            "output_dir": output_dir,
            "random_seed": random_seed,
        }
    )
    result = call(
        "run_scientific_analysis",
        payload,
        allowed_permissions={"filesystem_write"},
    )
    return result.model_dump(mode="json")


def _genomics_tool_mapping(tool_name: str) -> tuple[str, type[BaseModel], set[Permission]]:
    normalized = tool_name.strip().lower().replace("-", "_")
    mappings: dict[str, tuple[str, type[BaseModel], set[Permission]]] = {
        "zippy": (
            "prepare_zippy_pipeline",
            ZippyPipelineInput,
            {"filesystem_read", "filesystem_write", "code_exec"},
        ),
        "paragraph": (
            "prepare_paragraph_genotyping",
            ParagraphGenotypingInput,
            {"filesystem_read", "filesystem_write", "code_exec"},
        ),
        "expansionhunter_denovo": (
            "prepare_expansionhunter_denovo",
            ExpansionHunterDenovoInput,
            {"filesystem_read", "filesystem_write", "code_exec"},
        ),
        "ehdn": (
            "prepare_expansionhunter_denovo",
            ExpansionHunterDenovoInput,
            {"filesystem_read", "filesystem_write", "code_exec"},
        ),
        "gauchian": (
            "prepare_gauchian_calling",
            GauchianCallingInput,
            {"filesystem_read", "filesystem_write", "code_exec"},
        ),
        "ica": ("prepare_illumina_ica_request", IlluminaIcaRequestInput, {"network"}),
        "ica_sdk_python": ("prepare_illumina_ica_request", IlluminaIcaRequestInput, {"network"}),
    }
    if normalized not in mappings:
        raise ValueError(f"Unknown genomics tool {tool_name!r}.")
    return mappings[normalized]


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
