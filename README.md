# gdrive-mcp

Custom Google Drive MCP server. Full CRUD + soft-delete + folder allowlist + audit log. Service-account auth. Deployed on Railway.

## Tools

15 total: 12 curated (list_folder, search, read_file, download_file, get_metadata, create_folder, create_file, move, rename, copy, batch_move, plus prepare_delete + delete two-step) + prepare_purge_trash/purge_trash + whoami.

## Guardrails

1. Soft-delete to `_Trash` subfolder
2. Folder allowlist in `allowlist.json`
3. Dry-run on batch ops
4. Two-step confirmation tokens for destructive ops
5. Audit log to `mcp-audit.log` in audit folder

## Deploy

Railway from this repo. Env vars: `GOOGLE_SA_JSON`, `MCP_AUTH_TOKEN`, `AUDIT_FOLDER_ID`, `AUDIT_BUFFER_SIZE`, `AUDIT_FLUSH_INTERVAL_SECONDS`. `PORT` is set by Railway.

Health check: `GET /healthz` → `ok`. MCP endpoint: `POST /mcp` with `Authorization: Bearer <MCP_AUTH_TOKEN>`.
