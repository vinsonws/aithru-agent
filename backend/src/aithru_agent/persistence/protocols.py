from typing import Any

from pydantic import BaseModel


class WorkspaceFileContent(BaseModel):
    content: str | bytes
    media_type: str | None = None


StoreUpdate = dict[str, Any]

