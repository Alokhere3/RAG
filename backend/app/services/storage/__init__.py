"""Storage service interfaces and local implementation."""

from app.services.storage.local import LocalStorageService, storage_service

__all__ = ["LocalStorageService", "storage_service"]
