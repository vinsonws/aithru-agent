import base64
import binascii
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .base import AithruBaseModel


AgentWorkspaceImageContentEncoding = Literal["base64"]
AgentWorkspaceImageKind = Literal["workspace_image"]

SUPPORTED_WORKSPACE_IMAGE_MEDIA_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/webp", "image/gif"}
)
MAX_WORKSPACE_IMAGE_BYTES = 2 * 1024 * 1024


class AgentWorkspaceImageAttachment(AithruBaseModel):
    kind: AgentWorkspaceImageKind
    workspace_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    size: int = Field(gt=0)
    content_hash: str | None = None

    @field_validator("workspace_id", "content_hash")
    @classmethod
    def _strings_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("workspace image attachment fields cannot be blank")
        return stripped

    @field_validator("path")
    @classmethod
    def _path_must_reference_workspace_file(cls, value: str) -> str:
        return normalize_workspace_image_path(value)

    @field_validator("media_type")
    @classmethod
    def _media_type_must_be_supported_image(cls, value: str) -> str:
        return validate_workspace_image_media_type(value)

    @model_validator(mode="after")
    def _size_must_fit_image_limit(self) -> "AgentWorkspaceImageAttachment":
        validate_workspace_image_size(self.size)
        return self


AgentMessageAttachment = AgentWorkspaceImageAttachment


class AgentWorkspaceImageViewResult(AithruBaseModel):
    workspace_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    size: int = Field(gt=0)
    content_hash: str | None = None
    content_encoding: AgentWorkspaceImageContentEncoding = "base64"
    content_base64: str = Field(min_length=1)

    @field_validator("workspace_id", "content_hash")
    @classmethod
    def _strings_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("workspace image view fields cannot be blank")
        return stripped

    @field_validator("path")
    @classmethod
    def _path_must_reference_workspace_file(cls, value: str) -> str:
        return normalize_workspace_image_path(value)

    @field_validator("media_type")
    @classmethod
    def _media_type_must_be_supported_image(cls, value: str) -> str:
        return validate_workspace_image_media_type(value)

    @field_validator("content_base64")
    @classmethod
    def _content_must_be_base64(cls, value: str) -> str:
        try:
            base64.b64decode(value, validate=True)
        except binascii.Error as err:
            raise ValueError("content_base64 must be valid base64") from err
        return value

    @model_validator(mode="after")
    def _size_must_fit_image_limit(self) -> "AgentWorkspaceImageViewResult":
        validate_workspace_image_size(self.size)
        return self


def validate_workspace_image_media_type(value: str | None) -> str:
    if value is None:
        raise ValueError("Unsupported image media type: missing")
    media_type = value.strip().lower()
    if media_type not in SUPPORTED_WORKSPACE_IMAGE_MEDIA_TYPES:
        raise ValueError(
            "Unsupported image media type: "
            f"{value}. Supported image media types are: "
            f"{', '.join(sorted(SUPPORTED_WORKSPACE_IMAGE_MEDIA_TYPES))}"
        )
    return media_type


def validate_workspace_image_size(size: int) -> int:
    if size <= 0:
        raise ValueError("Workspace image size must be greater than 0 bytes")
    if size > MAX_WORKSPACE_IMAGE_BYTES:
        raise ValueError(
            "Workspace image exceeds maximum image size "
            f"of {MAX_WORKSPACE_IMAGE_BYTES} bytes"
        )
    return size


def normalize_workspace_image_path(value: str) -> str:
    raw = value.strip().replace("\\", "/")
    if not raw:
        raise ValueError("path must reference a workspace file")
    parts: list[str] = []
    for part in raw.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            if not parts:
                raise ValueError("path must reference a workspace file")
            parts.pop()
            continue
        parts.append(part)
    if not parts:
        raise ValueError("path must reference a workspace file")
    return "/" + "/".join(parts)


def workspace_image_content_base64(content: str | bytes) -> str:
    raw = content if isinstance(content, bytes) else content.encode("utf-8")
    return base64.b64encode(raw).decode("ascii")
