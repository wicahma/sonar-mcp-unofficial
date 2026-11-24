from __future__ import annotations

import json

from client import SonarError
from credential_manager import build_client


def main() -> int:
    client = build_client()
    try:
        version = client.request("GET", "/api/server/version")
        auth = client.request("GET", "/api/authentication/validate")
        user = client.request("GET", "/api/users/current")
        projects = client.request("GET", "/api/projects/search", params={"ps": 1})

        paging = projects.get("paging") if isinstance(projects, dict) else {}
        summary = {
            "version": version.strip() if isinstance(version, str) else version,
            "authenticated": auth.get("valid") if isinstance(auth, dict) else None,
            "user": (
                {"login": user.get("login"), "name": user.get("name")}
                if isinstance(user, dict)
                else None
            ),
            "projects_total": paging.get("total") if isinstance(paging, dict) else None,
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0
    except (SonarError, ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2, ensure_ascii=False))
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
