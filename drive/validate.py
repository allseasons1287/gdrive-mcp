"""Allowlist enforcement."""
import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from auth.client import get_drive_service

ALLOWLIST_PATH = Path(__file__).resolve().parent.parent / "allowlist.json"


@lru_cache(maxsize=1)
def load_allowlist() -> set[str]:
    with ALLOWLIST_PATH.open() as f:
        data = json.load(f)
    return set(data.get("allowed_folder_ids", []))


@lru_cache(maxsize=1024)
def is_allowed(file_id: str) -> bool:
    allowlist = load_allowlist()
    if file_id in allowlist:
        return True

    service = get_drive_service()
    visited = set()
    current = file_id
    while current and current not in visited:
        visited.add(current)
        try:
            meta = service.files().get(fileId=current, fields="parents", supportsAllDrives=True).execute()
        except Exception:
            return False
        parents = meta.get("parents", [])
        if not parents:
            return False
        for parent in parents:
            if parent in allowlist:
                return True
        current = parents[0]
    return False


class AllowlistViolation(Exception):
    def __init__(self, file_id: str):
        self.file_id = file_id
        super().__init__(f"File ID {file_id} is outside the allowlist. Refusing operation.")


def require_allowed(file_id: Optional[str]) -> None:
    if file_id is None:
        return
    if not is_allowed(file_id):
        raise AllowlistViolation(file_id)


def clear_cache() -> None:
    is_allowed.cache_clear()
