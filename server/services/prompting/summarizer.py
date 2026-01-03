from typing import Any


def make_summary_request(section_text: str, section_key: str) -> dict[str, Any]:
    system_prompt = """Ты создаёшь краткую сводку (summary) секции документа.

Твоя задача:
- Извлечь 3-7 ключевых пунктов из текста секции
- Каждый пункт должен быть кратким (1 предложение)
- Сохранить только самую важную информацию
- Избегать общих фраз типа "в разделе описано..."
"""

    user_prompt = f"""Создай summary для секции '{section_key}'.

Текст секции:
{section_text}

Верни только список ключевых пунктов (3-7 штук), каждый с новой строки, начиная с "- ".
"""

    return {
        "system": system_prompt,
        "user": user_prompt
    }


def parse_summary_response(response_text: str, section_key: str) -> dict[str, Any]:
    lines = response_text.strip().split("\n")
    points = []

    for line in lines:
        line = line.strip()
        if line.startswith("-") or line.startswith("•"):
            point = line.lstrip("-•").strip()
            if point:
                points.append(point)

    return {
        "section_key": section_key,
        "points": points
    }
