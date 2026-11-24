from __future__ import annotations

import argparse
import os
import sys

from mcp.server.fastmcp import FastMCP

from credential_manager import build_client
from tools import set_client
from tools import core, hotspots, issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Custom SonarQube MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default=os.environ.get("SONAR_MCP_TRANSPORT", "stdio"),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8124)
    args = parser.parse_args()

    client = build_client()
    try:
        client.check_credentials()
    except Exception as exc:
        sys.stderr.write(f"ERROR: SonarQube credentials unavailable: {exc}\n")
        return 1
    set_client(client)

    mcp = FastMCP("sonar-custom", host=args.host, port=args.port)
    for module in (core, issues, hotspots):
        module.register(mcp)

    try:
        mcp.run(transport=args.transport)
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
