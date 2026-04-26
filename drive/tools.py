"""The 12 curated Drive tools."""
import base64
import io
import secrets
from typing import Any, Optional

from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

from audit.logger import audit
from auth.client import get_drive_service
from drive.batch import batch_move_impl
from drive.trash import hard_purge, soft_delete
from drive.validate import (
    AllowlistViolation,
    clear_cache,
    require_allowed,
)

_pending_confirmations: dict[str, dict[str, Any]] = {}

DEFAULT_LIST_FIELDS = "id, name, mimeType, parents, modifiedTime, size, webViewLink"


def list_folder(folder_id: str, page_size: int = 100, page_token: Optional[str] = None) -> dict:
    require_allowed(folder_id)
    service = get_drive_service()
    result = service.files().list(
        q=f"'{folder_id}' in parents and trashed = false",
        pageSize=min(page_size, 1000),
        pageToken=page_token,
        fields=f"nextPageToken, files({DEFAULT_LIST_FIELDS})",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    return {
        "files": result.get("files", []),
        "next_page_token": result.get("nextPageToken"),
        "count": len(result.get("files", [])),
    }


def search(query: str, page_size: int = 50, page_token: Optional[str] = None) -> dict:
    service = get_drive_service()
    result = service.files().list(
        q=query,
        pageSize=min(page_size, 1000),
        pageToken=page_token,
        fields=f"nextPageToken, files({DEFAULT_LIST_FIELDS})",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    raw = result.get("files", [])
    from drive.validate import is_allowed
    filtered = [f for f in raw if is_allowed(f["id"])]
    return {
        "files": filtered,
        "next_page_token": result.get("nextPageToken"),
        "count": len(filtered),
        "filtered_out": len(raw) - len(filtered),
    }


def read_file(file_id: str, max_chars: int = 100000) -> dict:
    require_allowed(file_id)
    service = get_drive_service()

    meta = service.files().get(
        fileId=file_id, fields="id, name, mimeType, size", supportsAllDrives=True
    ).execute()

    mime = meta.get("mimeType", "")
    if mime.startswith("application/vnd.google-apps."):
        export_mime = {
            "application/vnd.google-apps.document": "text/plain",
            "application/vnd.google-apps.spreadsheet": "text/csv",
            "application/vnd.google-apps.presentation": "text/plain",
        }.get(mime, "text/plain")
        content_bytes = service.files().export(fileId=file_id, mimeType=export_mime).execute()
    else:
        content_bytes = service.files().get_media(fileId=file_id).execute()

    if isinstance(content_bytes, bytes):
        text = content_bytes.decode("utf-8", errors="replace")
    else:
        text = str(content_bytes)
    truncated = len(text) > max_chars
    return {
        "id": file_id,
        "name": meta.get("name"),
        "mime_type": mime,
        "content": text[:max_chars],
        "truncated": truncated,
        "total_chars": len(text),
    }


def download_file(file_id: str) -> dict:
    require_allowed(file_id)
    service = get_drive_service()

    meta = service.files().get(
        fileId=file_id, fields="id, name, mimeType, size", supportsAllDrives=True
    ).execute()

    request = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    raw = buf.getvalue()
    return {
        "id": file_id,
        "name": meta.get("name"),
        "mime_type": meta.get("mimeType"),
        "size_bytes": len(raw),
        "content_base64": base64.b64encode(raw).decode("ascii"),
    }


def get_metadata(file_id: str) -> dict:
    require_allowed(file_id)
    service = get_drive_service()
    return service.files().get(
        fileId=file_id,
        fields="id, name, mimeType, parents, createdTime, modifiedTime, size, webViewLink, owners, shared, trashed",
        supportsAllDrives=True,
    ).execute()


def create_folder(name: str, parent_id: str, caller: str = "unknown") -> dict:
    require_allowed(parent_id)
    service = get_drive_service()
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    created = service.files().create(
        body=metadata,
        fields="id, name, parents, webViewLink",
        supportsAllDrives=True,
    ).execute()
    audit("create_folder", source_id="", target=created["id"], result="ok", caller=caller)
    return created


def create_file(
    name: str,
    parent_id: str,
    content: str = "",
    mime_type: str = "text/plain",
    content_is_base64: bool = False,
    caller: str = "unknown",
) -> dict:
    require_allowed(parent_id)
    service = get_drive_service()

    if content_is_base64:
        raw = base64.b64decode(content)
    else:
        raw = content.encode("utf-8")

    metadata = {"name": name, "parents": [parent_id]}
    media = MediaIoBaseUpload(io.BytesIO(raw), mimetype=mime_type)
    created = service.files().create(
        body=metadata,
        media_body=media,
        fields="id, name, parents, mimeType, size, webViewLink",
        supportsAllDrives=True,
    ).execute()
    audit("create_file", source_id="", target=created["id"], result=f"ok ({len(raw)} bytes)", caller=caller)
    return created


def move(file_id: str, new_parent_id: str, caller: str = "unknown") -> dict:
    require_allowed(file_id)
    require_allowed(new_parent_id)
    service = get_drive_service()

    meta = service.files().get(
        fileId=file_id, fields="parents", supportsAllDrives=True
    ).execute()
    current_parents = meta.get("parents", [])
    if not current_parents:
        raise RuntimeError(f"File {file_id} has no current parent.")

    remove_parents = ",".join(current_parents)
    updated = service.files().update(
        fileId=file_id,
        addParents=new_parent_id,
        removeParents=remove_parents,
        fields="id, name, parents, webViewLink",
        supportsAllDrives=True,
    ).execute()
    clear_cache()
    audit("move", source_id=file_id, target=new_parent_id, result="ok", caller=caller)
    return updated


def rename(file_id: str, new_name: str, caller: str = "unknown") -> dict:
    require_allowed(file_id)
    service = get_drive_service()
    updated = service.files().update(
        fileId=file_id,
        body={"name": new_name},
        fields="id, name, parents, webViewLink",
        supportsAllDrives=True,
    ).execute()
    audit("rename", source_id=file_id, target=new_name, result="ok", caller=caller)
    return updated


def prepare_delete(file_id: str) -> dict:
    require_allowed(file_id)
    service = get_drive_service()
    meta = service.files().get(
        fileId=file_id, fields="id, name, mimeType, parents", supportsAllDrives=True
    ).execute()

    token = secrets.token_urlsafe(16)
    _pending_confirmations[token] = {"op": "delete", "file_id": file_id}
    return {
        "confirmation_token": token,
        "file_id": file_id,
        "file_name": meta.get("name"),
        "mime_type": meta.get("mimeType"),
        "next_step": f"Call delete(file_id='{file_id}', confirmation_token='{token}') to execute soft-delete.",
        "warning": "This moves the item to its parent's _Trash subfolder.",
    }


def delete(file_id: str, confirmation_token: str, caller: str = "unknown") -> dict:
    require_allowed(file_id)

    pending = _pending_confirmations.pop(confirmation_token, None)
    if pending is None:
        raise PermissionError("Invalid or expired confirmation token.")
    if pending.get("op") != "delete" or pending.get("file_id") != file_id:
        raise PermissionError("Confirmation token does not match this file_id.")

    result = soft_delete(file_id)
    clear_cache()
    audit("delete_soft", source_id=file_id, target=result["trash_folder_id"], result="ok", caller=caller)
    return {"soft_deleted": True, **result}


def copy(file_id: str, new_parent_id: str, new_name: Optional[str] = None, caller: str = "unknown") -> dict:
    require_allowed(file_id)
    require_allowed(new_parent_id)
    service = get_drive_service()

    body: dict[str, Any] = {"parents": [new_parent_id]}
    if new_name:
        body["name"] = new_name

    copied = service.files().copy(
        fileId=file_id,
        body=body,
        fields="id, name, parents, mimeType, webViewLink",
        supportsAllDrives=True,
    ).execute()
    audit("copy", source_id=file_id, target=copied["id"], result="ok", caller=caller)
    return copied


def batch_move(file_ids: list[str], target_parent_id: str, dry_run: bool = False, caller: str = "unknown") -> dict:
    result = batch_move_impl(file_ids, target_parent_id, dry_run=dry_run, caller=caller)
    if not dry_run:
        audit("batch_move", source_id=",".join(file_ids), target=target_parent_id,
              result=f"moved={result.get('moved_count', 0)} errors={len(result.get('errors', []))}",
              caller=caller)
    return result


def prepare_purge_trash(trash_folder_id: Optional[str] = None) -> dict:
    if trash_folder_id:
        require_allowed(trash_folder_id)

    service = get_drive_service()
    folders = []
    if trash_folder_id:
        folders = [trash_folder_id]
    else:
        result = service.files().list(
            q="name = '_Trash' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
            fields="files(id, name, parents)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        for f in result.get("files", []):
            try:
                require_allowed(f["id"])
                folders.append(f["id"])
            except AllowlistViolation:
                continue

    item_count = 0
    for fid in folders:
        contents = service.files().list(
            q=f"'{fid}' in parents and trashed = false",
            fields="files(id)",
            supportsAllDrives=True,
        ).execute()
        item_count += len(contents.get("files", []))

    token = secrets.token_urlsafe(16)
    _pending_confirmations[token] = {"op": "purge_trash", "folders": folders}
    return {
        "confirmation_token": token,
        "trash_folders": folders,
        "items_to_purge": item_count,
        "next_step": f"Call purge_trash(confirmation_token='{token}', confirm_purge='YES_I_MEAN_IT')",
        "warning": "HARD DELETE. Items NOT recoverable.",
    }


def purge_trash(confirmation_token: str, confirm_purge: str, caller: str = "unknown") -> dict:
    if confirm_purge != "YES_I_MEAN_IT":
        raise PermissionError("purge_trash requires confirm_purge='YES_I_MEAN_IT'.")

    pending = _pending_confirmations.pop(confirmation_token, None)
    if pending is None or pending.get("op") != "purge_trash":
        raise PermissionError("Invalid or expired confirmation token.")

    folders = pending.get("folders", [])
    total_purged = 0
    total_errors = 0
    for fid in folders:
        result = hard_purge(fid)
        total_purged += result["purged_count"]
        total_errors += len(result["errors"])
        audit("purge_trash", source_id=fid, target="", result=f"purged={result['purged_count']}", caller=caller)

    return {"purged_count": total_purged, "error_count": total_errors, "folders_processed": len(folders)}
