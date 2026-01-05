"""Sanitize facts.json to remove technical metrics before LLM sees them"""
import copy
from typing import Any


def sanitize_facts_for_llm(facts: dict[str, Any]) -> dict[str, Any]:
    """Remove technical metrics that should not appear in academic text

    Removes:
    - Repository URLs, commit hashes
    - Lines of code counts, percentages
    - Specific versions of dependencies
    - File paths and evidence trails

    Preserves:
    - Language names (without counts)
    - Framework names and types
    - Module structure and roles
    - Architecture patterns
    - API endpoints (without file paths)
    """
    if not facts:
        return {}

    clean = copy.deepcopy(facts)

    # Remove repo metadata (URLs, commit hashes)
    for key in ['repo', 'repository', 'commit', 'detected_at']:
        if key in clean:
            del clean[key]

    # Clean languages - keep names only, remove LOC/ratios/percentages
    if 'languages' in clean and isinstance(clean['languages'], list):
        clean['languages'] = [
            {'name': lang['name']}
            for lang in clean['languages']
            if isinstance(lang, dict) and
               lang.get('name') and
               lang.get('ratio', 0) > 0.05  # Only significant languages (>5%)
        ]

    # Clean frameworks - keep name/type only, remove versions
    if 'frameworks' in clean and isinstance(clean['frameworks'], list):
        clean['frameworks'] = [
            {
                'name': fw.get('name', 'Unknown'),
                'type': fw.get('type', 'unknown')
            }
            for fw in clean['frameworks']
            if isinstance(fw, dict) and fw.get('name')
        ]

    # Clean modules - remove evidence paths and file counts
    if 'modules' in clean and isinstance(clean['modules'], list):
        for mod in clean['modules']:
            if not isinstance(mod, dict):
                continue
            # Remove evidence (file paths)
            for key in ['evidence', 'path', 'files']:
                if key in mod:
                    del mod[key]
            # Keep: name, role, type, submodules count (but not paths)
            if 'submodules' in mod and isinstance(mod['submodules'], list):
                # Keep only count, not details
                mod['submodules_count'] = len(mod['submodules'])
                del mod['submodules']

    # Clean architecture - keep pattern names, remove evidence/confidence
    if 'architecture' in clean and isinstance(clean['architecture'], dict):
        arch = clean['architecture']
        for key in ['evidence', 'confidence']:
            if key in arch:
                del arch[key]
        # Keep: type, layers, patterns

    # Clean API - keep endpoints but remove file paths
    if 'api' in clean and isinstance(clean['api'], dict):
        if 'endpoints' in clean['api'] and isinstance(clean['api']['endpoints'], list):
            clean['api']['endpoints'] = [
                {
                    'method': ep.get('method', 'GET'),
                    'path': ep.get('path', '/')
                }
                for ep in clean['api']['endpoints']
                if isinstance(ep, dict)
            ][:10]  # Limit to first 10 endpoints

    # Clean frontend routes - keep paths only
    if 'frontend' in clean and isinstance(clean['frontend'], dict):
        if 'routes' in clean['frontend'] and isinstance(clean['frontend']['routes'], list):
            clean['frontend']['routes'] = [
                {'path': route.get('path', '/')}
                for route in clean['frontend']['routes']
                if isinstance(route, dict) and route.get('path')
            ][:10]  # Limit to first 10 routes

    # Clean dependencies - remove versions, keep only package names
    if 'dependencies' in clean:
        if isinstance(clean['dependencies'], list):
            clean['dependencies'] = [
                _strip_version(dep) if isinstance(dep, str) else str(dep)
                for dep in clean['dependencies']
            ]
        elif isinstance(clean['dependencies'], dict):
            # If dependencies is a dict like {name: version}
            clean['dependencies'] = list(clean['dependencies'].keys())

    # Remove any remaining LOC/metrics fields
    metrics_keys = [
        'lines_of_code', 'loc', 'sloc', 'file_count', 'total_files',
        'code_size', 'repository_size', 'commits_count'
    ]
    for key in metrics_keys:
        if key in clean:
            del clean[key]

    return clean


def _strip_version(dependency: str) -> str:
    """Remove version specifiers from dependency string

    Examples:
        django@>=5.0 -> django
        pytest==8.0.0 -> pytest
        redis~=5.0 -> redis
    """
    # Split by common version separators
    for sep in ['@', '==', '>=', '<=', '~=', '>', '<', '=']:
        if sep in dependency:
            return dependency.split(sep)[0].strip()
    return dependency.strip()


def get_sanitized_facts_summary(clean_facts: dict[str, Any], section_key: str) -> str:
    """Generate clean summary for a section without metrics

    Creates a brief text summary from sanitized facts,
    appropriate for the given section type.
    """
    if not clean_facts:
        return "Информация о проекте не доступна"

    parts = []

    # For analysis/requirements sections
    if section_key in ('analysis', 'requirements', 'intro'):
        if clean_facts.get('languages'):
            lang_names = [lang['name'] for lang in clean_facts['languages'][:3]]
            if lang_names:
                parts.append(f"Основные языки: {', '.join(lang_names)}")

        if clean_facts.get('frameworks'):
            fw_names = [fw['name'] for fw in clean_facts['frameworks'][:3]]
            if fw_names:
                parts.append(f"Используемые технологии: {', '.join(fw_names)}")

    # For architecture/design sections
    elif section_key in ('architecture', 'design', 'theory_1', 'theory_2'):
        if clean_facts.get('architecture', {}).get('type'):
            arch_type = clean_facts['architecture']['type']
            parts.append(f"Архитектурный подход: {arch_type}")

        if clean_facts.get('modules'):
            mod_count = len(clean_facts['modules'])
            parts.append(f"Система разделена на {mod_count} основных модулей")

            # Mention some module names
            mod_names = [
                m.get('name', '') for m in clean_facts['modules'][:4]
                if isinstance(m, dict) and m.get('name')
            ]
            if mod_names:
                parts.append(f"Ключевые модули: {', '.join(mod_names)}")

    # For implementation/development sections
    elif section_key in ('implementation', 'development', 'practice_1', 'practice_2'):
        if clean_facts.get('api', {}).get('endpoints'):
            count = len(clean_facts['api']['endpoints'])
            parts.append(f"Реализовано {count} API-маршрутов")

        if clean_facts.get('frontend', {}).get('routes'):
            count = len(clean_facts['frontend']['routes'])
            parts.append(f"Фронтенд содержит {count} маршрутов")

        if clean_facts.get('modules'):
            parts.append(f"Система состоит из {len(clean_facts['modules'])} функциональных модулей")

    # For testing/quality sections
    elif section_key in ('testing', 'quality', 'practice_3', 'practice_4'):
        test_frameworks = [
            fw['name'] for fw in clean_facts.get('frameworks', [])
            if fw.get('type') == 'testing'
        ]
        if test_frameworks:
            parts.append(f"Тестирование: {', '.join(test_frameworks)}")

        # Mention test modules if present
        test_modules = [
            m.get('name', '') for m in clean_facts.get('modules', [])
            if isinstance(m, dict) and
               m.get('role') == 'testing' or
               'test' in m.get('name', '').lower()
        ]
        if test_modules:
            parts.append(f"Тестовые модули: {', '.join(test_modules[:2])}")

    return "\n".join(parts) if parts else "Информация о структуре проекта"
