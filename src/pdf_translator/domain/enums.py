"""Domain enumerations for PDF Book Translator."""
from enum import Enum

class PageStatus(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    APPROVED_FOR_TRANSLATION = "APPROVED_FOR_TRANSLATION"
    TRANSLATING = "TRANSLATING"
    TRANSLATED = "TRANSLATED"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    EXPORTED = "EXPORTED"
    FAILED = "FAILED"

class ProviderType(str, Enum):
    OPENAI = "openai"
    GEMINI = "gemini"
    CLAUDE = "claude"
    BROWSER_CHATGPT = "browser_chatgpt"
    BROWSER_GEMINI = "browser_gemini"
    BROWSER_CLAUDE = "browser_claude"
    MOCK = "mock"
