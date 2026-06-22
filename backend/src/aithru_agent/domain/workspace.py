from typing import Literal, Self

from pydantic import Field, model_validator

from .base import AithruBaseModel


AgentWorkspaceStorageBackend = Literal["memory", "sqlite", "filesystem", "object_storage"]
AgentWorkspaceFileVersionOperation = Literal["write", "delete"]
AgentWorkspaceFileDiffOperation = Literal["added", "modified", "deleted"]
AgentWorkspaceRestoreOperation = Literal["restored", "deleted", "unchanged"]
AgentWorkspaceUploadSource = Literal["api"]
AgentWorkspaceUploadContentEncoding = Literal["base64"]


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
    version: int = Field(default=1, ge=1)
    file_version: int = Field(default=1, ge=1)
    content_hash: str | None = None
    created_at: str
    updated_at: str


class AgentWorkspaceFileReadResult(AithruBaseModel):
    path: str = Field(min_length=1)
    content: str | bytes
    media_type: str | None = None


class AgentWorkspaceFileDeleteResult(AithruBaseModel):
    path: str = Field(min_length=1)


class AgentWorkspaceFileVersion(AithruBaseModel):
    workspace_id: str
    path: str
    version: int = Field(ge=1)
    file_version: int = Field(ge=1)
    operation: AgentWorkspaceFileVersionOperation
    size: int = Field(ge=0)
    media_type: str | None = None
    content_hash: str | None = None
    created_at: str

    @model_validator(mode="after")
    def _delete_versions_have_no_content_hash(self) -> Self:
        if self.operation == "delete" and self.content_hash is not None:
            raise ValueError("delete versions must not include content_hash")
        return self


class AgentWorkspaceSnapshotFile(AithruBaseModel):
    workspace_id: str
    path: str
    size: int = Field(ge=0)
    media_type: str | None = None
    content_hash: str | None = None
    version: int = Field(ge=1)
    file_version: int = Field(ge=1)
    created_at: str
    updated_at: str


class AgentWorkspaceSnapshot(AithruBaseModel):
    workspace_id: str
    version: int = Field(ge=0)
    files: list[AgentWorkspaceSnapshotFile] = Field(default_factory=list)
    file_count: int = Field(ge=0)
    total_size: int = Field(ge=0)
    created_at: str

    @model_validator(mode="after")
    def _counts_match_files(self) -> Self:
        if self.file_count != len(self.files):
            raise ValueError("file_count must match files length")
        if self.total_size != sum(file.size for file in self.files):
            raise ValueError("total_size must match summed file sizes")
        return self


class AgentWorkspaceFileDiff(AithruBaseModel):
    path: str
    operation: AgentWorkspaceFileDiffOperation
    base_version: int | None = Field(default=None, ge=1)
    target_version: int | None = Field(default=None, ge=1)
    base_size: int | None = Field(default=None, ge=0)
    target_size: int | None = Field(default=None, ge=0)
    base_hash: str | None = None
    target_hash: str | None = None

    @model_validator(mode="after")
    def _operation_has_expected_versions(self) -> Self:
        if self.operation == "added" and self.base_version is not None:
            raise ValueError("added diffs must not include base_version")
        if self.operation == "deleted" and self.target_version is not None:
            raise ValueError("deleted diffs must not include target_version")
        if self.operation == "modified" and (self.base_version is None or self.target_version is None):
            raise ValueError("modified diffs require base_version and target_version")
        return self


class AgentWorkspaceDiff(AithruBaseModel):
    workspace_id: str
    base_version: int = Field(ge=0)
    target_version: int = Field(ge=0)
    changes: list[AgentWorkspaceFileDiff] = Field(default_factory=list)
    added_count: int = Field(ge=0)
    modified_count: int = Field(ge=0)
    deleted_count: int = Field(ge=0)

    @model_validator(mode="after")
    def _counts_match_changes(self) -> Self:
        added = sum(1 for change in self.changes if change.operation == "added")
        modified = sum(1 for change in self.changes if change.operation == "modified")
        deleted = sum(1 for change in self.changes if change.operation == "deleted")
        if (self.added_count, self.modified_count, self.deleted_count) != (added, modified, deleted):
            raise ValueError("diff counts must match changes")
        return self


class AgentWorkspaceTextPatchEdit(AithruBaseModel):
    old_text: str = Field(min_length=1)
    new_text: str
    replace_all: bool = False
    expected_replacements: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _single_replacement_expectation_is_one(self) -> Self:
        if not self.replace_all and self.expected_replacements not in {None, 1}:
            raise ValueError("single replacements can only expect one replacement")
        return self


class AgentWorkspaceTextPatchRequest(AithruBaseModel):
    path: str = Field(min_length=1)
    edits: list[AgentWorkspaceTextPatchEdit] = Field(min_length=1)
    media_type: str | None = None


class AgentWorkspacePatchResult(AithruBaseModel):
    workspace_id: str
    path: str
    version_before: int = Field(ge=1)
    version_after: int = Field(ge=1)
    file_version_before: int = Field(ge=1)
    file_version_after: int = Field(ge=1)
    size_before: int = Field(ge=0)
    size_after: int = Field(ge=0)
    replacement_count: int = Field(ge=1)
    content_hash: str | None = None

    @model_validator(mode="after")
    def _versions_advance(self) -> Self:
        if self.version_after <= self.version_before:
            raise ValueError("version_after must be greater than version_before")
        if self.file_version_after <= self.file_version_before:
            raise ValueError("file_version_after must be greater than file_version_before")
        return self


class AgentWorkspaceUploadResult(AithruBaseModel):
    workspace_id: str
    path: str
    file: AgentWorkspaceFile
    size: int = Field(ge=0)
    media_type: str | None = None
    content_encoding: AgentWorkspaceUploadContentEncoding = "base64"
    source: AgentWorkspaceUploadSource = "api"
    overwritten: bool = False

    @model_validator(mode="after")
    def _file_metadata_matches_upload(self) -> Self:
        if self.file.workspace_id != self.workspace_id:
            raise ValueError("upload file workspace must match upload workspace")
        if self.file.path != self.path:
            raise ValueError("upload file path must match upload path")
        if self.file.size != self.size:
            raise ValueError("upload file size must match upload size")
        if self.file.media_type != self.media_type:
            raise ValueError("upload file media type must match upload media type")
        return self


def apply_workspace_text_patch(
    content: str,
    request: AgentWorkspaceTextPatchRequest,
) -> tuple[str, int]:
    patched = content
    total_replacements = 0
    for index, edit in enumerate(request.edits, start=1):
        available = patched.count(edit.old_text)
        if available == 0:
            raise ValueError(f"Patch edit {index} did not match file content")
        replacement_count = available if edit.replace_all else 1
        if edit.expected_replacements is not None and replacement_count != edit.expected_replacements:
            raise ValueError(
                f"Patch edit {index} expected {edit.expected_replacements} replacements but found {replacement_count}"
            )
        patched = patched.replace(edit.old_text, edit.new_text, replacement_count)
        total_replacements += replacement_count
    return patched, total_replacements


class AgentWorkspaceRestoreChange(AithruBaseModel):
    path: str
    operation: AgentWorkspaceRestoreOperation
    source_version: int | None = Field(default=None, ge=1)
    target_version: int | None = Field(default=None, ge=1)
    new_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _operation_has_expected_versions(self) -> Self:
        if self.operation == "restored" and (self.target_version is None or self.new_version is None):
            raise ValueError("restored changes require target_version and new_version")
        if self.operation == "deleted" and self.new_version is None:
            raise ValueError("deleted changes require new_version")
        if self.operation == "unchanged" and self.new_version is not None:
            raise ValueError("unchanged changes must not include new_version")
        return self


class AgentWorkspaceRestoreResult(AithruBaseModel):
    workspace_id: str
    target_version: int = Field(ge=0)
    restored_version: int = Field(ge=0)
    changes: list[AgentWorkspaceRestoreChange] = Field(default_factory=list)
    restored_count: int = Field(ge=0)
    deleted_count: int = Field(ge=0)
    unchanged_count: int = Field(ge=0)

    @model_validator(mode="after")
    def _counts_match_changes(self) -> Self:
        restored = sum(1 for change in self.changes if change.operation == "restored")
        deleted = sum(1 for change in self.changes if change.operation == "deleted")
        unchanged = sum(1 for change in self.changes if change.operation == "unchanged")
        if (self.restored_count, self.deleted_count, self.unchanged_count) != (
            restored,
            deleted,
            unchanged,
        ):
            raise ValueError("restore counts must match changes")
        return self
