"""Buffered audit log writer."""
import io
import os
import threading
import time
from datetime import datetime, timezone

from googleapiclient.http import MediaIoBaseUpload

from auth.client import get_drive_service

AUDIT_FOLDER_ID = os.environ.get("AUDIT_FOLDER_ID", "1Uz46o5NAk3jtkEwA4UNbKWVHeWTVKadm")
BUFFER_SIZE = int(os.environ.get("AUDIT_BUFFER_SIZE", "10"))
FLUSH_INTERVAL = int(os.environ.get("AUDIT_FLUSH_INTERVAL_SECONDS", "30"))
LOG_FILENAME = "mcp-audit.log"

_buffer: list[str] = []
_buffer_lock = threading.Lock()
_last_flush = time.time()
_flush_timer: threading.Timer | None = None
_log_file_id: str | None = None


def _find_or_create_log_file() -> str:
    global _log_file_id
    if _log_file_id:
        return _log_file_id

    service = get_drive_service()
    query = (
        f"'{AUDIT_FOLDER_ID}' in parents "
        f"and name = '{LOG_FILENAME}' "
        f"and trashed = false"
    )
    result = service.files().list(
        q=query,
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    files = result.get("files", [])
    if files:
        _log_file_id = files[0]["id"]
        return _log_file_id

    metadata = {"name": LOG_FILENAME, "parents": [AUDIT_FOLDER_ID], "mimeType": "text/plain"}
    media = MediaIoBaseUpload(io.BytesIO(b""), mimetype="text/plain")
    created = service.files().create(
        body=metadata,
        media_body=media,
        fields="id",
        supportsAllDrives=True,
    ).execute()
    _log_file_id = created["id"]
    return _log_file_id


def audit(op: str, source_id: str = "", target: str = "", result: str = "ok", caller: str = "unknown") -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    line = f"{timestamp} | {op} | {source_id} | {target} | {result} | {caller}\n"

    global _last_flush, _flush_timer
    should_flush = False
    with _buffer_lock:
        _buffer.append(line)
        if len(_buffer) >= BUFFER_SIZE:
            should_flush = True
        elif _flush_timer is None:
            _flush_timer = threading.Timer(FLUSH_INTERVAL, flush_audit)
            _flush_timer.daemon = True
            _flush_timer.start()

    if should_flush:
        flush_audit()


def flush_audit() -> None:
    global _buffer, _last_flush, _flush_timer

    with _buffer_lock:
        if not _buffer:
            if _flush_timer:
                _flush_timer.cancel()
                _flush_timer = None
            return
        to_write = "".join(_buffer)
        _buffer.clear()
        if _flush_timer:
            _flush_timer.cancel()
            _flush_timer = None
        _last_flush = time.time()

    try:
        service = get_drive_service()
        log_id = _find_or_create_log_file()
        existing = service.files().get_media(fileId=log_id).execute()
        if isinstance(existing, bytes):
            existing_text = existing.decode("utf-8", errors="replace")
        else:
            existing_text = ""
        new_content = existing_text + to_write
        media = MediaIoBaseUpload(
            io.BytesIO(new_content.encode("utf-8")), mimetype="text/plain"
        )
        service.files().update(
            fileId=log_id,
            media_body=media,
            supportsAllDrives=True,
        ).execute()
    except Exception as e:
        import sys
        print(f"[audit] flush failed: {e}", file=sys.stderr)


def shutdown_audit() -> None:
    flush_audit()
