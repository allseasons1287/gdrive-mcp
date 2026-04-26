"""Drive API client singleton."""
from functools import lru_cache

from googleapiclient.discovery import Resource, build

from auth.service_account import load_credentials


@lru_cache(maxsize=1)
def get_drive_service() -> Resource:
    """Return a Drive v3 API client. Cached singleton."""
    creds = load_credentials()
    return build("drive", "v3", credentials=creds, cache_discovery=False)
