from __future__ import annotations

from mcp.types import ToolAnnotations

from tools import get_client
from tools.formatting import html_to_text


READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
WRITE = ToolAnnotations(destructiveHint=True, openWorldHint=True)

VALID_STATUSES = {"TO_REVIEW", "REVIEWED"}
VALID_RESOLUTIONS = {"SAFE", "FIXED"}


def _page(result: object) -> int:
    if isinstance(result, dict):
        paging = result.get("paging")
        if isinstance(paging, dict):
            return paging.get("total", 0) or 0
    return 0


def sonar_list_hotspots(
    project: str,
    status: str | None = None,
    resolution: str | None = None,
    branch: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    params: dict = {"project": project, "p": page, "ps": page_size}
    if status:
        params["status"] = status
    if resolution:
        params["resolution"] = resolution
    if branch:
        params["branch"] = branch

    result = get_client().request("GET", "/api/hotspots/search", params=params)
    data = result if isinstance(result, dict) else {}
    items = []
    for hotspot in data.get("hotspots", []) or []:
        if not isinstance(hotspot, dict):
            continue
        text_range = hotspot.get("textRange")
        line = text_range.get("startLine") if isinstance(text_range, dict) else None
        if line is None:
            line = hotspot.get("line")
        items.append(
            {
                "key": hotspot.get("key"),
                "component": hotspot.get("component"),
                "message": hotspot.get("message"),
                "status": hotspot.get("status"),
                "resolution": hotspot.get("resolution"),
                "line": line,
            }
        )
    return {"total": _page(data), "hotspots": items}


def sonar_get_hotspot_detail(hotspot_key: str) -> dict:
    result = get_client().request("GET", "/api/hotspots/show", params={"hotspot": hotspot_key})
    data = result if isinstance(result, dict) else {}
    rule = data.get("rule") if isinstance(data.get("rule"), dict) else {}

    why_source = rule.get("vulnerabilityDescription") or rule.get("riskDescription") or rule.get("htmlDesc")
    how_source = (
        rule.get("fixRecommendations")
        or rule.get("htmlExample")
        or rule.get("htmlExampleDesc")
    )
    notes = []
    if not why_source:
        notes.append("vulnerabilityDescription/htmlDesc tidak tersedia pada response hotspots/show versi ini.")
    if not how_source:
        notes.append("fixRecommendations/htmlExample tidak tersedia pada response hotspots/show versi ini.")

    text_range = data.get("textRange")
    if not isinstance(text_range, dict):
        text_range = {}
    location = {
        "component": data.get("component"),
        "path": data.get("path"),
        "textRange": {
            "startLine": text_range.get("startLine"),
            "endLine": text_range.get("endLine"),
            "startOffset": text_range.get("startOffset"),
            "endOffset": text_range.get("endOffset"),
        },
    }

    return {
        "key": data.get("key"),
        "project": data.get("project"),
        "component": data.get("component"),
        "message": data.get("message"),
        "status": data.get("status"),
        "resolution": data.get("resolution"),
        "assignee": data.get("assignee"),
        "author": data.get("author"),
        "location": location,
        "rule_key": rule.get("key"),
        "rule_name": rule.get("name"),
        "why": html_to_text(why_source),
        "how_to_fix": html_to_text(how_source),
        "notes": notes,
    }


def sonar_update_hotspot_status(
    hotspot_key: str,
    status: str,
    resolution: str | None = None,
    comment: str | None = None,
    confirm: bool = False,
) -> dict:
    if confirm is not True:
        raise ValueError("sonar_update_hotspot_status requires confirm=True")
    if status not in VALID_STATUSES:
        raise ValueError(f"Status '{status}' tidak valid. Pilihan: {', '.join(sorted(VALID_STATUSES))}")
    if resolution is not None and resolution not in VALID_RESOLUTIONS:
        raise ValueError(
            f"Resolution '{resolution}' tidak valid. Pilihan: {', '.join(sorted(VALID_RESOLUTIONS))}"
        )
    if status == "REVIEWED" and resolution is None:
        raise ValueError("Resolution wajib untuk status REVIEWED (SAFE atau FIXED)")

    payload: dict = {"hotspot": hotspot_key, "status": status}
    if resolution:
        payload["resolution"] = resolution
    if comment:
        payload["comment"] = comment
    get_client().request("POST", "/api/hotspots/change_status", data=payload)

    return {
        "hotspot_key": hotspot_key,
        "status": status,
        "resolution": resolution,
        "changed": True,
    }


def register(mcp) -> None:
    mcp.tool(name="sonar_list_hotspots", annotations=READ_ONLY)(sonar_list_hotspots)
    mcp.tool(name="sonar_get_hotspot_detail", annotations=READ_ONLY)(sonar_get_hotspot_detail)
    mcp.tool(name="sonar_update_hotspot_status", annotations=WRITE)(sonar_update_hotspot_status)
