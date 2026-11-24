from __future__ import annotations

from mcp.types import ToolAnnotations

from tools import get_client


READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)


def sonar_health() -> dict:
    result = get_client().request("GET", "/api/server/version")
    if isinstance(result, dict):
        version = result.get("version", "")
    elif isinstance(result, str):
        version = result.strip()
    else:
        version = str(result)
    return {"ok": True, "version": version}


def sonar_whoami() -> dict:
    result = get_client().request("GET", "/api/users/current")
    data = result if isinstance(result, dict) else {}
    return {
        "login": data.get("login"),
        "name": data.get("name"),
        "email": data.get("email"),
    }


def sonar_search_projects(q: str | None = None, page: int = 1, page_size: int = 50) -> dict:
    params: dict = {"p": page, "ps": page_size}
    path = "/api/projects/search_my_projects"
    if q is not None:
        path = "/api/projects/search"
        params["q"] = q
    result = get_client().request("GET", path, params=params)
    data = result if isinstance(result, dict) else {}
    paging = data.get("paging") if isinstance(data.get("paging"), dict) else {}
    projects = []
    for item in data.get("projects", []) or []:
        if not isinstance(item, dict):
            continue
        projects.append({"key": item.get("key"), "name": item.get("name")})
    return {"total": paging.get("total", 0), "projects": projects}


def register(mcp) -> None:
    mcp.tool(name="sonar_health", annotations=READ_ONLY)(sonar_health)
    mcp.tool(name="sonar_whoami", annotations=READ_ONLY)(sonar_whoami)
    mcp.tool(name="sonar_search_projects", annotations=READ_ONLY)(sonar_search_projects)
