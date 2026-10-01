"""Address router - resolves email addresses to SubBox paths."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.registry.models import Registry


class Router:
    def __init__(self, registry: Registry, domain: str):
        self.registry = registry
        self.domain = domain

    def resolve(self, address: str) -> Optional[str]:
        """Resolve address to local_part. Returns None if invalid/unknown."""
        if "@" not in address:
            return None
        local, dom = address.rsplit("@", 1)
        if dom != self.domain:
            return None
        entry = self.registry.get(local)
        if not entry:
            return None
        return local

    def is_active(self, address: str) -> bool:
        local = self.resolve(address)
        if not local:
            return False
        entry = self.registry.get(local)
        return entry is not None and entry.get("status") == "active"

    def box_path_for(self, address: str) -> Optional[Path]:
        local = self.resolve(address)
        if not local:
            return None
        return self.registry.root / "boxes" / local
