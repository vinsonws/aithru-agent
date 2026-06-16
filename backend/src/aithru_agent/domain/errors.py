from enum import StrEnum


class AgentErrorCode(StrEnum):
    BAD_REQUEST = "BAD_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    AUTHZ_DENIED = "AUTHZ_DENIED"
    SKILL_NOT_FOUND = "SKILL_NOT_FOUND"
    TOOL_DENIED = "TOOL_DENIED"
    TOOL_FAILED = "TOOL_FAILED"
    APPROVAL_NOT_FOUND = "APPROVAL_NOT_FOUND"
    RUN_NOT_RESUMABLE = "RUN_NOT_RESUMABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AgentError(Exception):
    def __init__(self, code: AgentErrorCode | str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)
        self.message = message

