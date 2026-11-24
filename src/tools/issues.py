from __future__ import annotations

from mcp.types import ToolAnnotations

from client import SonarError
from tools import get_client
from tools.formatting import html_to_text


READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
WRITE = ToolAnnotations(destructiveHint=True, openWorldHint=True)

STATUS_TRANSITIONS = {
    "false_positive": "falsepositive",
    "confirmed": "confirm",
    "open": "reopen",
    "resolved": "resolve",
}


def _csv(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        return ",".join(str(item) for item in value)
    return str(value)


def _page(result: object) -> int:
    if isinstance(result, dict):
        paging = result.get("paging")
        if isinstance(paging, dict):
            return paging.get("total", 0) or 0
    return 0


def _flow_summary(flows: object) -> str:
    lines = []
    for flow in flows or []:
        if not isinstance(flow, dict):
            continue
        for location in flow.get("locations", []) or []:
            if not isinstance(location, dict):
                continue
            text_range = location.get("textRange")
            line = text_range.get("startLine") if isinstance(text_range, dict) else None
            component = location.get("component") or ""
            where = f"{component}:{line}" if line else str(component)
            message = str(location.get("msg") or "").strip()
            lines.append(f"- {where} {message}".rstrip())
    return "\n".join(lines)


def sonar_list_issues(
    project: str | None = None,
    branch: str | None = None,
    statuses: object = None,
    in_new_code_period: bool = False,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    params: dict = {"p": page, "ps": page_size}
    if project:
        params["projects"] = project
    if branch:
        params["branch"] = branch
    csv_statuses = _csv(statuses)
    if csv_statuses:
        params["statuses"] = csv_statuses
    if in_new_code_period:
        params["inNewCodePeriod"] = "true"

    result = get_client().request("GET", "/api/issues/search", params=params)
    data = result if isinstance(result, dict) else {}
    items = []
    for issue in data.get("issues", []) or []:
        if not isinstance(issue, dict):
            continue
        text_range = issue.get("textRange")
        line = text_range.get("startLine") if isinstance(text_range, dict) else None
        if line is None:
            line = issue.get("line")
        items.append(
            {
                "key": issue.get("key"),
                "rule_key": issue.get("ruleKey"),
                "project": issue.get("project"),
                "component": issue.get("component"),
                "line": line,
                "message": issue.get("message"),
                "severity": issue.get("severity"),
                "type": issue.get("type"),
                "status": issue.get("status"),
                "creation_date": issue.get("creationDate"),
            }
        )
    return {"total": _page(data), "issues": items}


def sonar_get_issue_detail(issue_key: str) -> dict:
    result = get_client().request(
        "GET",
        "/api/issues/search",
        params={"issues": issue_key, "additionalFields": "transitions,rules"},
    )
    data = result if isinstance(result, dict) else {}
    issues = [item for item in (data.get("issues") or []) if isinstance(item, dict)]
    issue = issues[0] if issues else {}

    paths = {}
    for component in data.get("components", []) or []:
        if isinstance(component, dict) and component.get("key"):
            paths[component["key"]] = component.get("path")

    rule_key = issue.get("ruleKey")
    rule = {}
    if rule_key:
        for candidate in data.get("rules", []) or []:
            if isinstance(candidate, dict) and candidate.get("key") == rule_key:
                rule = candidate
                break
        if not rule:
            try:
                rule_result = get_client().request("GET", "/api/rules/show", params={"key": rule_key})
                if isinstance(rule_result, dict):
                    rule = rule_result.get("rule") if isinstance(rule_result.get("rule"), dict) else rule_result
            except SonarError:
                rule = {}

    text_range = issue.get("textRange")
    if not isinstance(text_range, dict):
        text_range = {}
    location = {
        "component": issue.get("component"),
        "path": paths.get(issue.get("component")),
        "textRange": {
            "startLine": text_range.get("startLine"),
            "endLine": text_range.get("endLine"),
            "startOffset": text_range.get("startOffset"),
            "endOffset": text_range.get("endOffset"),
        },
    }

    message = str(issue.get("message") or "").strip()
    why_parts = [part for part in (message, html_to_text(rule.get("htmlDesc"))) if part]
    fix_parts = [
        part
        for part in (
            html_to_text(rule.get("htmlExample") or rule.get("htmlExampleDesc")),
            _flow_summary(issue.get("flows")),
        )
        if part
    ]
    flows = []
    for flow in issue.get("flows", []) or []:
        if not isinstance(flow, dict):
            continue
        locations = []
        for item in flow.get("locations", []) or []:
            if isinstance(item, dict):
                locations.append(
                    {
                        "component": item.get("component"),
                        "textRange": item.get("textRange"),
                        "msg": item.get("msg"),
                    }
                )
        flows.append({"locations": locations})

    return {
        "key": issue.get("key"),
        "rule_key": rule_key,
        "rule_name": rule.get("name"),
        "project": issue.get("project"),
        "component": issue.get("component"),
        "message": issue.get("message"),
        "severity": issue.get("severity"),
        "type": issue.get("type"),
        "status": issue.get("status"),
        "resolution": issue.get("resolution"),
        "effort": issue.get("effort"),
        "tags": issue.get("tags") or [],
        "location": location,
        "why": "\n\n".join(why_parts),
        "how_to_fix": "\n\n".join(fix_parts),
        "flows": flows,
        "transitions": issue.get("transitions") or [],
    }


def sonar_get_issue_summary(
    project: str | None = None,
    branch: str | None = None,
    in_new_code_period: bool = False,
) -> dict:
    params: dict = {"facets": "statuses,severities,types,projects,rules", "ps": 1}
    if project:
        params["projects"] = project
    if branch:
        params["branch"] = branch
    if in_new_code_period:
        params["inNewCodePeriod"] = "true"

    result = get_client().request("GET", "/api/issues/search", params=params)
    data = result if isinstance(result, dict) else {}
    facets = {name: {} for name in ("statuses", "severities", "types", "projects", "rules")}
    for facet in data.get("facets", []) or []:
        if not isinstance(facet, dict):
            continue
        name = facet.get("property")
        if name not in facets:
            continue
        values = {}
        for item in facet.get("values", []) or []:
            if isinstance(item, dict) and item.get("val") is not None:
                values[str(item["val"])] = item.get("count", 0)
        facets[name] = values

    hotspots = {"to_review": 0, "reviewed": 0}
    hotspot_params: dict = {"ps": 1}
    if project:
        hotspot_params["project"] = project
    if branch:
        hotspot_params["branch"] = branch
    for status, key in (("TO_REVIEW", "to_review"), ("REVIEWED", "reviewed")):
        params_for_status = dict(hotspot_params, status=status)
        hotspot_result = get_client().request("GET", "/api/hotspots/search", params=params_for_status)
        hotspots[key] = _page(hotspot_result)

    return {
        "total": _page(data),
        "statuses": facets["statuses"],
        "severities": facets["severities"],
        "types": facets["types"],
        "projects": facets["projects"],
        "rules": facets["rules"],
        "hotspots": hotspots,
    }


def sonar_update_issue_status(
    issue_key: str,
    status: str,
    comment: str | None = None,
    confirm: bool = False,
) -> dict:
    if confirm is not True:
        raise ValueError("sonar_update_issue_status requires confirm=True")
    transition = STATUS_TRANSITIONS.get(status)
    if transition is None:
        raise ValueError(
            f"Status '{status}' tidak dikenal. Pilihan: {', '.join(sorted(STATUS_TRANSITIONS))}"
        )

    result = get_client().request(
        "GET",
        "/api/issues/search",
        params={"issues": issue_key, "additionalFields": "transitions"},
    )
    data = result if isinstance(result, dict) else {}
    transitions = []
    for issue in data.get("issues", []) or []:
        if not isinstance(issue, dict):
            continue
        for item in issue.get("transitions", []) or []:
            if isinstance(item, str):
                transitions.append(item)
            elif isinstance(item, dict) and item.get("key"):
                transitions.append(item["key"])
    if transition not in transitions:
        raise ValueError(
            f"Transisi '{transition}' tidak tersedia untuk {issue_key}. Transisi yang diizinkan: {transitions}"
        )

    get_client().request(
        "POST",
        "/api/issues/do_transition",
        data={"issue": issue_key, "transition": transition},
    )

    comment_posted = False
    if comment:
        try:
            get_client().request(
                "POST", "/api/issues/add_comment", data={"issue": issue_key, "text": comment}
            )
            comment_posted = True
        except SonarError as exc:
            raise SonarError(
                exc.status,
                f"Status {issue_key} sudah berubah ke {status}, tetapi comment gagal: {exc.message}",
            ) from exc

    return {
        "issue_key": issue_key,
        "status": status,
        "transition": transition,
        "changed": True,
        "comment_posted": comment_posted,
    }


def register(mcp) -> None:
    mcp.tool(name="sonar_list_issues", annotations=READ_ONLY)(sonar_list_issues)
    mcp.tool(name="sonar_get_issue_detail", annotations=READ_ONLY)(sonar_get_issue_detail)
    mcp.tool(name="sonar_get_issue_summary", annotations=READ_ONLY)(sonar_get_issue_summary)
    mcp.tool(name="sonar_update_issue_status", annotations=WRITE)(sonar_update_issue_status)
