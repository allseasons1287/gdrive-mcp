"""Auth layer — service account credential loading + Drive API client."""
from auth.client import get_drive_service
from auth.service_account import load_credentials

__all__ = ["get_drive_service", "load_credentials"]
