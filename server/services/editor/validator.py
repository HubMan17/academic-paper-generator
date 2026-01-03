from dataclasses import asdict
from .schema import QualityReport, DocumentEdited
from .analyzer import analyze_document


def validate_document(document: DocumentEdited) -> QualityReport:
    sections_list = [
        {"key": key, "title": key, "text": text}
        for key, text in document.sections.items()
    ]
    return analyze_document(sections_list)


def compare_quality_reports(
    before: QualityReport,
    after: QualityReport,
) -> dict:
    improvements = []
    regressions = []
    unchanged = []

    chars_diff = after.total_chars - before.total_chars
    chars_percent = (chars_diff / before.total_chars * 100) if before.total_chars > 0 else 0
    if abs(chars_percent) > 5:
        if chars_diff > 0:
            improvements.append(f"Объём увеличен на {chars_percent:.1f}%")
        else:
            unchanged.append(f"Объём уменьшен на {abs(chars_percent):.1f}%")

    before_repeats = len(before.global_repeats)
    after_repeats = len(after.global_repeats)
    if after_repeats < before_repeats:
        improvements.append(f"Повторы уменьшены: {before_repeats} → {after_repeats}")
    elif after_repeats > before_repeats:
        regressions.append(f"Повторы увеличены: {before_repeats} → {after_repeats}")

    before_short = len(before.short_sections)
    after_short = len(after.short_sections)
    if after_short < before_short:
        improvements.append(f"Коротких секций меньше: {before_short} → {after_short}")
    elif after_short > before_short:
        regressions.append(f"Коротких секций больше: {before_short} → {after_short}")

    before_style = len(before.style_issues)
    after_style = len(after.style_issues)
    if after_style < before_style:
        improvements.append(f"Проблем стиля меньше: {before_style} → {after_style}")
    elif after_style > before_style:
        regressions.append(f"Проблем стиля больше: {before_style} → {after_style}")

    before_empty = len(before.empty_sections)
    after_empty = len(after.empty_sections)
    if after_empty < before_empty:
        improvements.append(f"Пустых секций меньше: {before_empty} → {after_empty}")
    elif after_empty > before_empty:
        regressions.append(f"Пустых секций больше: {before_empty} → {after_empty}")

    before_markers = sum(before.style_marker_counts.values())
    after_markers = sum(after.style_marker_counts.values())
    if after_markers < before_markers:
        improvements.append(f"Шаблонных фраз меньше: {before_markers} → {after_markers}")
    elif after_markers > before_markers:
        regressions.append(f"Шаблонных фраз больше: {before_markers} → {after_markers}")

    return {
        "improvements": improvements,
        "regressions": regressions,
        "unchanged": unchanged,
        "summary": {
            "before": {
                "total_chars": before.total_chars,
                "total_words": before.total_words,
                "global_repeats": before_repeats,
                "short_sections": before_short,
                "style_issues": before_style,
                "style_markers": before_markers,
            },
            "after": {
                "total_chars": after.total_chars,
                "total_words": after.total_words,
                "global_repeats": after_repeats,
                "short_sections": after_short,
                "style_issues": after_style,
                "style_markers": after_markers,
            },
        },
        "is_improved": len(improvements) > len(regressions),
    }


def check_edit_success(
    quality_report_before: QualityReport,
    quality_report_after: QualityReport,
) -> tuple[bool, list[str]]:
    issues = []

    if quality_report_after.total_chars < quality_report_before.total_chars * 0.7:
        issues.append("Текст сократился более чем на 30%")

    if len(quality_report_after.empty_sections) > len(quality_report_before.empty_sections):
        issues.append("Появились пустые секции")

    if len(quality_report_after.global_repeats) > len(quality_report_before.global_repeats) * 1.5:
        issues.append("Количество повторов значительно увеличилось")

    success = len(issues) == 0
    return success, issues


def quality_report_to_dict(report: QualityReport) -> dict:
    return {
        "version": report.version,
        "total_chars": report.total_chars,
        "total_words": report.total_words,
        "sections": [
            {
                "key": s.key,
                "title": s.title,
                "char_count": s.char_count,
                "word_count": s.word_count,
                "sentence_count": s.sentence_count,
                "avg_sentence_length": s.avg_sentence_length,
                "repeat_phrases": [
                    {"phrase": r.phrase, "count": r.count}
                    for r in s.repeat_phrases[:5]
                ],
                "term_candidates": s.term_candidates[:10],
                "issues": s.issues,
            }
            for s in report.sections
        ],
        "global_repeats": [
            {
                "phrase": r.phrase,
                "count": r.count,
                "sections": list(set(loc[0] for loc in r.locations)),
            }
            for r in report.global_repeats
        ],
        "term_candidates": report.term_candidates[:30],
        "short_sections": report.short_sections,
        "empty_sections": report.empty_sections,
        "style_issues": report.style_issues,
        "style_marker_counts": report.style_marker_counts,
        "total_style_markers": sum(report.style_marker_counts.values()),
    }
