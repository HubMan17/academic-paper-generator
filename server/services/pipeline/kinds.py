from enum import Enum


class ArtifactKind(str, Enum):
    OUTLINE = "outline:v1"
    CONTEXT_PACK = "context_pack:{key}:v1"
    SECTION = "section:{key}:v1"
    SECTION_SUMMARY = "section_summary:{key}:v1"
    LLM_TRACE = "llm_trace:{key}:v1"
    DOCUMENT_DRAFT = "document_draft:v1"
    TOC = "toc:v1"
    QUALITY_REPORT = "quality_report:v1"

    @classmethod
    def context_pack(cls, key: str) -> str:
        return cls.CONTEXT_PACK.value.replace("{key}", key)

    @classmethod
    def section(cls, key: str) -> str:
        return cls.SECTION.value.replace("{key}", key)

    @classmethod
    def section_summary(cls, key: str) -> str:
        return cls.SECTION_SUMMARY.value.replace("{key}", key)

    @classmethod
    def llm_trace(cls, key: str) -> str:
        return cls.LLM_TRACE.value.replace("{key}", key)


def parse_kind(kind: str) -> tuple[str, str | None]:
    if ":v1" not in kind:
        return kind, None

    parts = kind.replace(":v1", "").split(":")
    if len(parts) == 2:
        return parts[0], parts[1]
    return parts[0], None
