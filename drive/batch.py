"""Batch operations — atomic-ish bulk moves with dry-run support."""
from typing import Any

from auth.client import get_drive_service
from drive.validate import require_allowed, clear_cache


def batch_move_impl(
    file_ids: list[str], target_parent_id: str, dry_run: bool = False, caller: str = "unknown"
) -> dict[str, Any]:
    if len(file_ids) > 50:
        raise ValueError(f"batch_move accepts up to 50 IDs at once. Got {len(file_ids)}.")

    require_allowed(target_parent_id)
    for fid in file_ids:
        require_allowed(fid)

    service = get_drive_service()
    plan = []
    for fid in file_ids:
        meta = service.files().get(
            fileId=fid, fields="id, name, parents", supportsAllDrives=True
        ).execute()
        plan.append({
            "id": fid,
            "name": meta.get("name"),
            "current_parents": meta.get("parents", []),
            "new_parent": target_parent_id,
        })

    if dry_run:
        return {"dry_run": True, "plan": plan, "would_move_count": len(plan)}

    moved = []
    errors = []
    for entry in plan:
        try:
            current_parents = entry["current_parents"]
            remove_parents = ",".join(current_parents) if current_parents else None
            updated = service.files().update(
                fileId=entry["id"],
                addParents=target_parent_id,
                removeParents=remove_parents,
                fields="id, name, parents",
                supportsAllDrives=True,
            ).execute()
            moved.append({
                "id": updated["id"],
                "name": updated["name"],
                "new_parents": updated.get("parents", []),
            })
        except Exception as e:
            errors.append({"id": entry["id"], "error": str(e)})

    clear_cache()
    return {"dry_run": False, "moved_count": len(moved), "moved": moved, "errors": errors}
