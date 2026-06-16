from typing import Literal

from .base import AithruBaseModel


AgentWorkspaceStorageBackend = Literal["memory", "sqlite", "filesystem", "object_storage"]


class AgentWorkspace(AithruBaseModel):
    id: str
    org_id: str
    thread_id: str | None = None
    run_id: str | None = None
    storage_backend: AgentWorkspaceStorageBackend
    created_at: str


class AgentWorkspaceFile(AithruBaseModel):
    workspace_id: str
    path: str
    size: int
    media_type: str | None = None
    created_at: str
    updated_at: str
