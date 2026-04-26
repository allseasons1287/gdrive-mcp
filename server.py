"""FastMCP server — exposes Drive tools over HTTP/streamable transport."""
import os
import sys
from typing import Optional

from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

from audit.logger import shutdown_audit
from auth.service_account import get_service_account_email
from drive import tools

import os as _os
mcp = FastMCP(
    "gdrive-mcp",
    streamable_http_path="/mcp",
    stateless_http=True,
)
# Disable DNS rebinding protection — Railway puts us behind a public domain
try:
    mcp.settings.streamable_http_validate_dns_rebinding = False
except Exception:
    pass


@mcp.tool()
def list_folder(folder_id: str, page_size: int = 100, page_token: Optional[str] = None) -> dict:
    """List immediate children of a folder. Allowlist-enforced."""
    return tools.list_folder(folder_id, page_size, page_token)


@mcp.tool()
def search(query: str, page_size: int = 50, page_token: Optional[str] = None) -> dict:
    """Search Drive with full Drive query syntax. Results filtered to allowlist."""
    return tools.search(query, page_size, page_token)


@mcp.tool()
def read_file(file_id: str, max_chars: int = 100000) -> dict:
    """Read text content of a file."""
    return tools.read_file(file_id, max_chars)


@mcp.tool()
def download_file(file_id: str) -> dict:
    """Download binary content as base64."""
    return tools.download_file(file_id)


@mcp.tool()
def get_metadata(file_id: str) -> dict:
    """Return full metadata for a file or folder."""
    return tools.get_metadata(file_id)


@mcp.tool()
def create_folder(name: str, parent_id: str) -> dict:
    """Create a folder under parent_id."""
    return tools.create_folder(name, parent_id, caller="cowork")


@mcp.tool()
def create_file(
    name: str,
    parent_id: str,
    content: str = "",
    mime_type: str = "text/plain",
    content_is_base64: bool = False,
) -> dict:
    """Create a file with content."""
    return tools.create_file(name, parent_id, content, mime_type, content_is_base64, caller="cowork")


@mcp.tool()
def move(file_id: str, new_parent_id: str) -> dict:
    """Move file_id to new_parent_id."""
    return tools.move(file_id, new_parent_id, caller="cowork")


@mcp.tool()
def rename(file_id: str, new_name: str) -> dict:
    """Rename file_id."""
    return tools.rename(file_id, new_name, caller="cowork")


@mcp.tool()
def prepare_delete(file_id: str) -> dict:
    """Step 1 of soft-delete. Returns a confirmation token."""
    return tools.prepare_delete(file_id)


@mcp.tool()
def delete(file_id: str, confirmation_token: str) -> dict:
    """Step 2 of soft-delete. Requires token from prepare_delete()."""
    return tools.delete(file_id, confirmation_token, caller="cowork")


@mcp.tool()
def copy(file_id: str, new_parent_id: str, new_name: Optional[str] = None) -> dict:
    """Copy file_id into new_parent_id."""
    return tools.copy(file_id, new_parent_id, new_name, caller="cowork")


@mcp.tool()
def batch_move(file_ids: list[str], target_parent_id: str, dry_run: bool = False) -> dict:
    """Move up to 50 files atomically."""
    return tools.batch_move(file_ids, target_parent_id, dry_run, caller="cowork")


@mcp.tool()
def prepare_purge_trash(trash_folder_id: Optional[str] = None) -> dict:
    """Step 1 of HARD delete."""
    return tools.prepare_purge_trash(trash_folder_id)


@mcp.tool()
def purge_trash(confirmation_token: str, confirm_purge: str) -> dict:
    """Step 2 of HARD delete. Requires confirm_purge='YES_I_MEAN_IT'."""
    return tools.purge_trash(confirmation_token, confirm_purge, caller="cowork")


@mcp.tool()
def whoami() -> dict:
    """Return service account email + allowlist summary."""
    from drive.validate import load_allowlist
    return {
        "service_account_email": get_service_account_email(),
        "allowlist_folder_ids": list(load_allowlist()),
        "audit_folder_id": os.environ.get("AUDIT_FOLDER_ID"),
    }


class BearerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, expected_token: str):
        super().__init__(app)
        self.expected_token = expected_token

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/healthz":
            return await call_next(request)

        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return JSONResponse({"error": "missing or malformed Authorization header"}, status_code=401)
        token = header[len("Bearer "):].strip()
        if token != self.expected_token:
            return JSONResponse({"error": "invalid token"}, status_code=401)
        return await call_next(request)


async def healthz(request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


def main():
    auth_token = os.environ.get("MCP_AUTH_TOKEN")
    if not auth_token:
        print("[server] FATAL: MCP_AUTH_TOKEN env var not set", file=sys.stderr)
        sys.exit(1)
    if len(auth_token) < 16:
        print("[server] FATAL: MCP_AUTH_TOKEN must be at least 16 chars", file=sys.stderr)
        sys.exit(1)

    try:
        sa_email = get_service_account_email()
        print(f"[server] service account: {sa_email}", file=sys.stderr)
    except Exception as e:
        print(f"[server] FATAL: service account did not load: {e}", file=sys.stderr)
        sys.exit(1)

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))

    print(f"[server] listening on http://{host}:{port} (streamable-http)", file=sys.stderr)

    app = mcp.streamable_http_app()
    app.add_middleware(BearerAuthMiddleware, expected_token=auth_token)
    app.routes.insert(0, Route("/healthz", healthz, methods=["GET"]))

    import uvicorn
    try:
        uvicorn.run(app, host=host, port=port, log_level="info", proxy_headers=True, forwarded_allow_ips="*")
    finally:
        shutdown_audit()


if __name__ == "__main__":
    main()
