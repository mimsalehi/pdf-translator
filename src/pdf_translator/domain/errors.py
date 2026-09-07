"""Domain exceptions for PDF Book Translator."""

class DomainError(Exception):
    """Base domain error."""
    pass

class ProjectNotFoundError(DomainError):
    def __init__(self, project_id: str):
        super().__init__(f"Project '{project_id}' was not found.")

class PageNotFoundError(DomainError):
    def __init__(self, project_id: str, page_number: int):
        super().__init__(f"Page {page_number} in project '{project_id}' was not found.")

class ProfileNotFoundError(DomainError):
    def __init__(self, profile_id: str):
        super().__init__(f"Translation profile '{profile_id}' was not found.")

class InvalidStateTransitionError(DomainError):
    def __init__(self, current_status: str, target_status: str, reason: str = ""):
        message = f"Cannot transition page from '{current_status}' to '{target_status}'."
        if reason:
            message += f" Reason: {reason}"
        super().__init__(message)

class TranslationProviderError(DomainError):
    def __init__(self, provider: str, details: str):
        super().__init__(f"Translation provider '{provider}' failed: {details}")

class ExportError(DomainError):
    def __init__(self, details: str):
        super().__init__(f"Export failed: {details}")
