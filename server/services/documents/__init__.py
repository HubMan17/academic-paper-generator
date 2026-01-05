"""
DEPRECATED: This module is legacy and will be removed in a future version.

Use services.pipeline.DocumentRunner for new document generation.

This module is kept for backward compatibility with:
- tasks/document_tasks.py (Celery tasks)
- apps/projects/views.py (old API endpoints)

Migration guide:
- DocumentService.generate_outline() -> pipeline.steps.outline.ensure_outline_v2()
- DocumentService.generate_section_text() -> pipeline.steps.section_generate.ensure_section()
- DocumentService.build_context_pack() -> pipeline.steps.context_pack.ensure_context_pack()
"""
import warnings

from .service import DocumentService, FactsNotFound, SectionBusy

__all__ = ['DocumentService', 'FactsNotFound', 'SectionBusy']

_DEPRECATION_WARNING_SHOWN = False


def _warn_deprecation():
    global _DEPRECATION_WARNING_SHOWN
    if not _DEPRECATION_WARNING_SHOWN:
        warnings.warn(
            "services.documents is deprecated. Use services.pipeline.DocumentRunner instead.",
            DeprecationWarning,
            stacklevel=3
        )
        _DEPRECATION_WARNING_SHOWN = True
