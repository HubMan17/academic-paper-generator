"""Clean up service markers and formatting artifacts from generated text"""
import re


def sanitize_section_text(text: str, section_key: str = "") -> str:
    """Remove all service markers while preserving valid markdown

    Removes:
    - Section key markers (#theory_1, #practice_2, etc.)
    - Standalone numbering headers (##1., ##2.1, etc.)
    - HTML comments
    - LLM meta-commentary ([generated], MOCK, etc.)
    - Excessive blank lines

    Preserves:
    - Valid markdown headers with content
    - Paragraph structure
    - Formatting (bold, italic, lists)
    """
    if not text:
        return text

    # Remove section key markers (#theory_1, #practice_2, #intro, #conclusion, etc.)
    text = re.sub(r'#(theory|practice|intro|conclusion)(_\d+)?\b', '', text)

    # Remove standalone numbering headers like "##1." or "##2.1" without content
    # But preserve headers with actual titles like "## 1.1 Название раздела"
    text = re.sub(r'^##\s*\d+\.(\d+\.)*\s*$', '', text, flags=re.MULTILINE)

    # Remove HTML comments (<!-- anything -->)
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)

    # Remove common LLM meta-commentary patterns
    meta_patterns = [
        r'\[.*?generated.*?\]',               # [generated], [auto-generated]
        r'\(.*?auto-generated.*?\)',          # (auto-generated text)
        r'Это (?:тестовый|сгенерированный) текст.*?(?:MOCK|mock).*',  # MOCK mentions
        r'\[PLACEHOLDER\]',                   # [PLACEHOLDER]
        r'\[TODO.*?\]',                       # [TODO: something]
        r'\[INTERNAL.*?\]',                   # [INTERNAL NOTE]
    ]
    for pattern in meta_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)

    # Remove multiple consecutive blank lines (more than 2 blank lines = 3+ newlines)
    # Keep at most 2 blank lines (3 newlines) for readability
    text = re.sub(r'\n{4,}', '\n\n\n', text)

    # Clean up leading/trailing whitespace
    text = text.strip()

    # Ensure document ends with exactly one newline (convention)
    if text and not text.endswith('\n'):
        text += '\n'

    return text


def sanitize_document_text(full_text: str) -> str:
    """Sanitize entire assembled document

    Additional document-level cleanup beyond section-level sanitization.
    """
    text = sanitize_section_text(full_text)

    # Remove duplicate section headers (LLM sometimes repeats them)
    # Match: "## Some Header" followed by blank lines and the same header again
    text = re.sub(
        r'(#{1,3}\s+.+?)\n+\1',
        r'\1',
        text,
        flags=re.MULTILINE
    )

    # Remove orphaned markdown header markers without content
    # E.g., "##" or "###" alone on a line
    text = re.sub(r'^#{1,6}\s*$', '', text, flags=re.MULTILINE)

    # Normalize multiple spaces to single space (but preserve indentation)
    lines = []
    for line in text.split('\n'):
        # Don't touch lines that are indented (code blocks, lists)
        if line.startswith((' ', '\t', '-', '*', '1.', '2.', '3.')):
            lines.append(line)
        else:
            # Normalize multiple spaces in regular text
            lines.append(re.sub(r' {2,}', ' ', line))

    text = '\n'.join(lines)

    return text


def detect_service_markers(text: str) -> dict[str, list[str]]:
    """Detect remaining service markers for validation/debugging

    Returns dict with marker types and their matches.
    Useful for testing that sanitization worked correctly.
    """
    markers = {
        'section_keys': [],
        'numbering_headers': [],
        'html_comments': [],
        'meta_commentary': [],
    }

    # Section key markers
    section_key_matches = re.findall(r'#(theory|practice|intro|conclusion)(_\d+)?', text)
    if section_key_matches:
        markers['section_keys'] = [f"#{match[0]}{match[1]}" for match in section_key_matches]

    # Standalone numbering headers
    numbering_matches = re.findall(r'^##\s*\d+\.(\d+\.)*\s*$', text, flags=re.MULTILINE)
    if numbering_matches:
        markers['numbering_headers'] = numbering_matches

    # HTML comments
    html_matches = re.findall(r'<!--.*?-->', text, flags=re.DOTALL)
    if html_matches:
        markers['html_comments'] = [match[:50] + '...' if len(match) > 50 else match
                                     for match in html_matches]

    # Meta commentary
    meta_matches = re.findall(r'\[(?:generated|PLACEHOLDER|TODO|INTERNAL).*?\]', text, flags=re.IGNORECASE)
    if meta_matches:
        markers['meta_commentary'] = meta_matches

    return markers
