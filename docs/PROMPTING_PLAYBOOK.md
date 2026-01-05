# Prompting Playbook

Technical documentation for maintaining quality and traceability in generated academic documents.

## Overview

This document describes the mechanisms implemented to ensure:
1. **Traceability** - every generated piece of text can be traced back to its source
2. **Groundedness** - LLM cannot invent facts, only transform provided data
3. **Anti-wateriness** - practice sections contain concrete technical content, not generic filler

## 1. Prompt Versioning & Fingerprinting (PR9)

### Problem
Without versioning, it's impossible to reproduce or debug generated content.

### Solution

#### Prompt Version
```python
# schema.py
PROMPT_VERSION = "v1.0.0"
```

Version is embedded in every ContextPack and propagated to all artifacts.

#### Prompt Fingerprint
```python
# slicer.py
def compute_prompt_fingerprint(
    system_prompt: str,
    user_prompt: str,
    fact_keys: list[str],
    budget_json: str
) -> str:
    """SHA256 hash of prompts + facts + budget"""
```

The fingerprint uniquely identifies the exact input that produced output.

### Artifact Data Structure
```json
{
  "prompt_version": "v1.0.0",
  "prompt_fingerprint": "sha256:abc123...",
  "meta": {
    "prompt_version": "v1.0.0",
    "prompt_fingerprint": "sha256:abc123..."
  }
}
```

### Traceability Chain
```
section_generate artifact
  → context_pack_artifact_id
    → prompt_version
    → prompt_fingerprint
    → selected_facts.keys[]
```

Any generated section can be traced back to:
- Exact prompt version used
- Exact facts included
- Budget constraints applied

---

## 2. Grounded Editing (PR10)

### Problem
Editor could "invent" content not present in the original text or facts.

### Solution

#### Three Editor Levels
| Level | Name | Grounding | Use Case |
|-------|------|-----------|----------|
| L1 | Basic | None | Quick fixes, formatting |
| L2 | Medium | Required | Style improvement |
| L3 | University | Required | Full academic editing |

#### Grounding Rule for L2/L3
```python
GROUNDING_RULE_L2_L3 = """
GROUNDING RULE (CRITICAL):
- ONLY use information from ORIGINAL TEXT and FACTS
- DO NOT add new information not present in sources
- DO NOT invent statistics, dates, or technical details
- If information is insufficient, mark as [NEEDS_DATA]
- Every claim must be traceable to ORIGINAL TEXT or FACTS
"""
```

#### JSON Output Schema
```python
EDITOR_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "edited_text": {"type": "string"},
        "facts_used": {
            "type": "array",
            "items": {"type": "string"},
            "description": "IDs of facts from context_pack used"
        },
        "changes_made": {
            "type": "array",
            "items": {"type": "string"}
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1}
    },
    "required": ["edited_text", "facts_used", "changes_made", "confidence"]
}
```

#### Validation
```python
def validate_grounded_output(
    output: EditorSectionOutput,
    available_fact_ids: set[str],
    level: EditorLevel
) -> list[str]:
    """Returns list of validation errors"""
```

L2/L3 outputs are rejected if:
- `facts_used` is empty
- `facts_used` contains IDs not in `available_fact_ids`

---

## 3. Quality Report (PR11)

### Problem
Generated documents need objective quality metrics suitable for academic review.

### Metrics Collected

#### Practice Block Validation
```python
PRACTICE_REQUIRED_BLOCKS = [
    ("code_sample", r"```[\w]*\n"),
    ("diagram_or_figure", r"(?:рис(?:унок)?\.?\s*\d|figure\s*\d|схема|диаграмма)"),
    ("table", r"\|[^\n]+\|\n\|[-:\s|]+\|"),
    ("algorithm", r"(?:алгоритм|псевдокод|algorithm|шаги?\s*:)"),
]
```

#### Terminology Consistency
```python
TERMINOLOGY_GROUPS = [
    ["пользователь", "юзер", "user"],
    ["приложение", "апп", "application", "app"],
    # ...
]
```

Detects mixed usage of synonyms within the same document.

#### QualityStats Fields
```python
@dataclass
class QualityStats:
    total_chars: int
    word_count: int
    section_count: int
    avg_section_length: float
    sections_below_min: list[str]
    sections_above_max: list[str]

    # PR11 additions
    repetition_score: float  # 0-1, lower is better
    section_length_warnings: list[SectionLengthWarning]
    missing_required_blocks: list[PracticeBlockCheck]
    terminology_inconsistencies: list[TerminologyIssue]
    suggested_fixes: list[SuggestedFix]
```

---

## 4. Anti-Template Guardrails (PR12)

### Problem
Practice sections often contain generic "water" text:
- "The system provides..."
- "Modern methods are used..."
- Abstract descriptions without concrete details

### Solution

#### System Prompt Injection
For practice sections (`implementation`, `testing`, `api`, etc.):

```python
PRACTICE_GUARDRAILS = """
MANDATORY REQUIREMENTS FOR PRACTICE SECTIONS:

1. CONCRETE ENTITIES (minimum 2):
   Reference real project entities from FACTS (models, services, components).
   Examples: User, Document, Section, ContextPack, LLMClient, Artifact.

2. ALGORITHM OR PSEUDOCODE (minimum 1):
   Include numbered steps with Input/Output.
   Format:
   **Algorithm [name]:**
   1. Input: ...
   2. Step: ...
   3. Output: ...

3. TABLE (minimum 1):
   Add markdown table with data.
   Examples: API endpoints, data models, artifacts, dependencies.

FORBIDDEN:
- Generic phrases without specifics ("system provides", "modern methods")
- Abstract descriptions without FACTS references
- Text without technical details
"""
```

#### Content Validation
```python
def validate_practice_content(
    text: str,
    min_entities: int = 2,
    require_algorithm: bool = True,
    require_table: bool = True
) -> PracticeValidationResult:
```

#### Detection Patterns

**Entities** (CamelCase + known terms):
```python
ENTITY_PATTERNS = [
    r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b',  # CamelCase
    r'\bUser\b', r'\bDocument\b', r'\bSection\b', ...
]
```

**Algorithms**:
```python
ALGORITHM_PATTERNS = [
    r'(?i)\*\*алгоритм\b',
    r'(?i)\balgorithm\b',
    r'(?i)\bшаги?\b.*:',
    r'(?i)\bsteps?\b.*:',
    r'(?i)\binput\s*:',
    r'(?i)\boutput\s*:',
]
```

**Tables**:
```python
TABLE_PATTERN = r'\|[^\n]+\|[\r\n]+\s*\|[\s\-:]+\|'
```

#### Validation Score
```python
score = 0.0
if entities >= min_entities: score += 0.4
if has_algorithm: score += 0.3
if has_table: score += 0.3
```

#### Integration Point
Validation runs in `section_generate.py` for every practice section:
```python
if is_practice_section(section_key):
    validation_result = validate_practice_content(content_text)
    practice_validation = validation_result.to_dict()

    if not validation_result.is_valid:
        logger.warning(f"Practice section {section_key} validation warnings: ...")
```

Results stored in:
- `artifact.meta.practice_validation`
- `llm_trace.practice_validation`

---

## Best Practices

### Adding New Prompts
1. Increment `PROMPT_VERSION` for breaking changes
2. Document changes in this playbook
3. Add tests for new validation rules

### Debugging Generation Issues
1. Find the artifact by section_key
2. Get `context_pack_artifact_id` from meta
3. Check `prompt_fingerprint` to identify exact inputs
4. Review `selected_facts.keys` for included facts
5. Check `practice_validation` for content quality

### Improving Content Quality
1. Expand `ENTITY_PATTERNS` for domain-specific terms
2. Add new `ALGORITHM_PATTERNS` for other code formats
3. Extend `PRACTICE_REQUIRED_BLOCKS` in quality.py
4. Update `TERMINOLOGY_GROUPS` for consistency checking

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| v1.0.0 | 2026-01-05 | Initial release with PR9-PR12 features |
