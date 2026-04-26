"""Soft-delete logic — moves files to a /Trash subfolder rather than hard-deleting."""
from datetime import datetime, timezone
from typing import Optional

from auth.client import get_drive_service

TRASH_FOLDER_NAME = "_Trash"


def get_or_create_trash_folder(parent_id: str) -> str:
    service = get_drive_service()

    query = (
        f"'{parent_id}' in parents "
        f"and name = '{TRASH_FOLDER_NAME}' "
        f"and mimeType = 'application/vnd.google-apps.folder' "
        f"and trashed = false"
    )
    result = service.files().list(
        q=query,
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    existing = result.get("files", [])
    if existing:
        return existing[0]["id"]

    metadata = {
        "name": TRASH_FOLDER_NAME,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    created = service.files().create(
        body=metadata,
        fields="id",
        supportsAllDrives=True,
    ).execute()
    return created["id"]


def soft_delete(file_id: str) -> dict:
    service = get_drive_service()

    meta = service.files().get(
        fileId=file_id,
        fields="id, name, parents",
        supportsAllDrives=True,
    ).execute()
    name = meta["name"]
    parents = meta.get("parents", [])
    if not parents:
        raise RuntimeError(f"File {file_id} has no parent — cannot soft-delete.")
    current_parent = parents[0]

    parent_meta = service.files().get(
        fileId=current_parent,
        fields="name",
        supportsAllDrives=True,
    ).execute()
    if parent_meta["name"] == TRASH_FOLDER_NAME:
        raise RuntimeError(f"File {file_id} is already in _Trash.")

    trash_id = get_or_create_trash_folder(current_parent)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    new_name = f"{name}.deleted_{timestamp}"

    updated = service.files().update(
        fileId=file_id,
        body={"name": new_name},
        addParents=trash_id,
        removeParents=current_parent,
        fields="id, name, parents",
        supportsAllDrives=True,
    ).execute()

    return {
        "id": updated["id"],
        "new_name": updated["name"],
        "trash_folder_id": trash_id,
        "original_parent": current_parent,
    }


def hard_purge(trash_folder_id: Optional[str] = None) -> dict:
    service = get_drive_service()
    purged = []
    errors = []

    folders_to_purge = []
    if trash_folder_id:
        folders_to_purge = [trash_folder_id]
    else:
        result = service.files().list(
            q=f"name = '{TRASH_FOLDER_NAME}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
            fields="files(id, name, parents)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        folders_to_purge = [f["id"] for f in result.get("files", [])]

    for tf_id in folders_to_purge:
        contents = service.files().list(
            q=f"'{tf_id}' in parents and trashed = false",
            fields="files(id, name)",
            supportsAllDrives=True,
        ).execute()
        for item in contents.get("files", []):
            try:
                service.files().delete(fileId=item["id"], supportsAllDrives=True).execute()
                purged.append({"id": item["id"], "name": item["name"]})
            except Exception as e:
                errors.append({"id": item["id"], "error": str(e)})

    return {"purged_count": len(purged), "purged": purged, "errors": errors}
