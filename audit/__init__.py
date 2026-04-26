"""Audit log — buffered writes to mcp-audit.log inside an allowlisted folder."""
from audit.logger import audit, flush_audit, shutdown_audit

__all__ = ["audit", "flush_audit", "shutdown_audit"]
