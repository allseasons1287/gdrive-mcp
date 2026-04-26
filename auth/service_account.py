"""Load Google service account credentials from environment."""
import json
import os
from functools import lru_cache

from google.oauth2 import service_account

SCOPES = ["https://www.googleapis.com/auth/drive"]


@lru_cache(maxsize=1)
def load_credentials() -> service_account.Credentials:
    raw = os.environ.get("GOOGLE_SA_JSON")
    if not raw:
        raise RuntimeError(
            "GOOGLE_SA_JSON env var not set. "
            "Paste the full service account JSON contents (not a file path) into Railway env."
        )

    try:
        info = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"GOOGLE_SA_JSON is not valid JSON: {e}. "
            "Make sure you pasted the entire service account key file contents."
        ) from e

    required_fields = {"type", "project_id", "private_key", "client_email"}
    missing = required_fields - set(info.keys())
    if missing:
        raise RuntimeError(
            f"GOOGLE_SA_JSON missing required fields: {missing}."
        )

    return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)


def get_service_account_email() -> str:
    return load_credentials().service_account_email
