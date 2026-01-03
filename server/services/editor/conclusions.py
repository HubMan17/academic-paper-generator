from typing import Optional

from services.llm import LLMClient
from .schema import ChapterConclusion
from . import prompts


async def generate_chapter_conclusions(
    llm_client: LLMClient,
    outline: dict,
    section_summaries: list[dict],
    idempotency_prefix: Optional[str] = None,
) -> list[ChapterConclusion]:
    conclusions: list[ChapterConclusion] = []

    chapters = outline.get("chapters", [])
    summaries_by_key = {s["key"]: s for s in section_summaries}

    for chapter in chapters:
        chapter_key = chapter.get("key", "")
        chapter_title = chapter.get("title", "")
        chapter_sections = chapter.get("sections", [])

        chapter_summaries = []
        for section in chapter_sections:
            section_key = section.get("key", "")
            if section_key in summaries_by_key:
                chapter_summaries.append({
                    "title": section.get("title", ""),
                    "summary": summaries_by_key[section_key].get("summary", ""),
                })

        if not chapter_summaries:
            continue

        idempotency_key = None
        if idempotency_prefix:
            idempotency_key = f"{idempotency_prefix}:conclusion:{chapter_key}"

        conclusion = await _generate_chapter_conclusion(
            llm_client=llm_client,
            chapter_key=chapter_key,
            chapter_title=chapter_title,
            section_summaries=chapter_summaries,
            idempotency_key=idempotency_key,
        )

        if conclusion:
            conclusions.append(conclusion)

    return conclusions


async def _generate_chapter_conclusion(
    llm_client: LLMClient,
    chapter_key: str,
    chapter_title: str,
    section_summaries: list[dict],
    idempotency_key: Optional[str] = None,
) -> Optional[ChapterConclusion]:
    user_prompt = prompts.get_chapter_conclusion_user(
        chapter_title=chapter_title,
        section_summaries=section_summaries,
    )

    result = await llm_client.generate_json(
        system_prompt=prompts.CHAPTER_CONCLUSION_SYSTEM,
        user_prompt=user_prompt,
        schema=_CONCLUSION_SCHEMA,
        idempotency_key=idempotency_key,
    )

    bullets = result.content.get("bullets", [])

    if not bullets:
        return None

    return ChapterConclusion(
        chapter_key=chapter_key,
        chapter_title=chapter_title,
        bullets=bullets[:7],
    )


async def generate_final_conclusion(
    llm_client: LLMClient,
    document_title: str,
    chapter_conclusions: list[ChapterConclusion],
    original_conclusion: str,
    idempotency_key: Optional[str] = None,
) -> str:
    conclusions_data = [
        {
            "chapter_title": c.chapter_title,
            "bullets": c.bullets,
        }
        for c in chapter_conclusions
    ]

    user_prompt = prompts.get_final_conclusion_user(
        document_title=document_title,
        chapter_conclusions=conclusions_data,
        original_conclusion=original_conclusion,
    )

    result = await llm_client.generate_text(
        system_prompt=prompts.FINAL_CONCLUSION_SYSTEM,
        user_prompt=user_prompt,
        max_tokens=2000,
        idempotency_key=idempotency_key,
    )

    return result.content.strip()


def chapter_conclusions_to_dict(conclusions: list[ChapterConclusion]) -> dict:
    return {
        "version": "v1",
        "chapters": [
            {
                "chapter_key": c.chapter_key,
                "chapter_title": c.chapter_title,
                "bullets": c.bullets,
            }
            for c in conclusions
        ],
        "count": len(conclusions),
    }


_CONCLUSION_SCHEMA = {
    "type": "object",
    "properties": {
        "bullets": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 3,
            "maxItems": 7,
        },
    },
    "required": ["bullets"],
}
