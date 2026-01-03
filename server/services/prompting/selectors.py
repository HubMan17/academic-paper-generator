from typing import Any
from .schema import SectionSpec, FactRef


def _evidence_to_strings(evidence: list[Any]) -> list[str]:
    result = []
    for e in evidence:
        if isinstance(e, dict):
            result.append(e.get("path", str(e)))
        else:
            result.append(str(e))
    return result


def _extract_facts_from_analyzer(facts: dict[str, Any]) -> list[dict[str, Any]]:
    extracted = []

    if facts.get("repo"):
        repo = facts["repo"]
        extracted.append({
            "id": "repo_info",
            "tags": ["project_name", "description", "repo"],
            "key_path": "repo",
            "text": f"Repository: {repo.get('url', 'unknown')}",
            "details": f"Commit: {repo.get('commit', 'unknown')}, Detected: {repo.get('detected_at', '')}"
        })

    for i, lang in enumerate(facts.get("languages", [])):
        extracted.append({
            "id": f"lang_{i}",
            "tags": ["tech_stack", "languages", "purpose"],
            "key_path": f"languages.{lang.get('name', 'unknown')}",
            "text": f"Language: {lang.get('name', 'unknown')} ({lang.get('ratio', 0):.0%})",
            "details": f"{lang.get('lines_of_code', 0)} lines of code"
        })

    for i, fw in enumerate(facts.get("frameworks", [])):
        extracted.append({
            "id": f"fw_{i}",
            "tags": ["tech_stack", "frameworks", "purpose"],
            "key_path": f"frameworks.{fw.get('name', 'unknown')}",
            "text": f"Framework: {fw.get('name', 'unknown')} ({fw.get('type', 'unknown')})",
            "details": f"Type: {fw.get('type', 'unknown')}"
        })

    arch = facts.get("architecture")
    if arch:
        arch_type = arch.get("type", "unknown")
        confidence = arch.get("confidence", 0)
        evidence = arch.get("evidence", [])
        evidence_strs = _evidence_to_strings(evidence)
        extracted.append({
            "id": "architecture",
            "tags": ["architecture", "layers", "infra"],
            "key_path": "architecture.type",
            "text": f"Architecture: {arch_type} (confidence: {confidence:.0%})",
            "details": ", ".join(evidence_strs) if evidence_strs else "No evidence"
        })

    for i, mod in enumerate(facts.get("modules", [])):
        extracted.append({
            "id": f"mod_{i}",
            "tags": ["architecture", "modules", "layers"],
            "key_path": f"modules.{mod.get('name', 'unknown')}",
            "text": f"Module: {mod.get('name', 'unknown')} ({mod.get('role', 'unknown')})",
            "details": f"Path: {mod.get('path', '')}, Submodules: {len(mod.get('submodules', []))}"
        })

    api = facts.get("api", {})
    endpoints = api.get("endpoints", [])
    if endpoints:
        extracted.append({
            "id": "api_summary",
            "tags": ["api", "endpoints"],
            "key_path": "api.summary",
            "text": f"API: {len(endpoints)} endpoints",
            "details": f"Total endpoints: {api.get('total_count', len(endpoints))}"
        })

        for i, ep in enumerate(endpoints[:20]):
            extracted.append({
                "id": f"endpoint_{i}",
                "tags": ["api", "endpoints", "auth"] if ep.get("auth_required") else ["api", "endpoints"],
                "key_path": f"api.endpoints.{ep.get('handler', i)}",
                "text": f"{ep.get('method', 'GET')} {ep.get('full_path', ep.get('path', '/'))}",
                "details": f"Handler: {ep.get('handler', 'unknown')}, File: {ep.get('file', '')}"
            })

    for i, route in enumerate(facts.get("frontend_routes", [])):
        extracted.append({
            "id": f"route_{i}",
            "tags": ["frontend", "routes"],
            "key_path": f"frontend_routes.{route.get('name', i)}",
            "text": f"Route: {route.get('path', '/')} -> {route.get('component', 'unknown')}",
            "details": f"Name: {route.get('name', '')}, File: {route.get('file', '')}"
        })

    for i, model in enumerate(facts.get("models", [])):
        extracted.append({
            "id": f"model_{i}",
            "tags": ["models", "storage", "api"],
            "key_path": f"models.{model.get('name', 'unknown')}",
            "text": f"Model: {model.get('name', 'unknown')} (table: {model.get('table', 'unknown')})",
            "details": f"Fields: {len(model.get('fields', []))}, Relationships: {len(model.get('relationships', []))}"
        })

    runtime = facts.get("runtime", {})
    deps = runtime.get("dependencies", [])
    if deps:
        top_deps = deps[:10]
        deps_text = ", ".join(f"{d.get('name')}@{d.get('version', '*')}" for d in top_deps)
        extracted.append({
            "id": "dependencies",
            "tags": ["tech_stack", "dependencies"],
            "key_path": "runtime.dependencies",
            "text": f"Dependencies: {len(deps)} packages",
            "details": deps_text + ("..." if len(deps) > 10 else "")
        })

    build_files = runtime.get("build_files", [])
    if build_files:
        extracted.append({
            "id": "build_files",
            "tags": ["infra", "build"],
            "key_path": "runtime.build_files",
            "text": f"Build files: {len(build_files)}",
            "details": ", ".join(build_files[:5])
        })

    entrypoints = runtime.get("entrypoints", [])
    if entrypoints:
        extracted.append({
            "id": "entrypoints",
            "tags": ["infra", "entrypoints"],
            "key_path": "runtime.entrypoints",
            "text": f"Entry points: {len(entrypoints)}",
            "details": ", ".join(entrypoints[:5])
        })

    return extracted


def select_facts(
    spec: SectionSpec,
    facts: dict[str, Any],
    max_facts: int = 30
) -> tuple[list[dict[str, Any]], list[FactRef]]:
    selected_facts = []
    fact_refs = []

    if not isinstance(facts, dict):
        return selected_facts, fact_refs

    if "facts" in facts and isinstance(facts["facts"], list):
        facts_list = facts["facts"]
    else:
        facts_list = _extract_facts_from_analyzer(facts)

    for fact in facts_list:
        if not isinstance(fact, dict):
            continue

        fact_id = fact.get("id", "")
        fact_tags = fact.get("tags", [])
        fact_key = fact.get("key_path", "")

        if not fact_id:
            continue

        selected = False
        reason = ""

        if fact_key in spec.fact_keys:
            selected = True
            reason = f"key:{fact_key}"

        if not selected:
            for tag in spec.fact_tags:
                if tag in fact_tags:
                    selected = True
                    reason = f"tag:{tag}"
                    break

        if selected:
            selected_facts.append(fact)
            fact_refs.append(FactRef(fact_id=fact_id, reason=reason))

            if len(selected_facts) >= max_facts:
                break

    return selected_facts, fact_refs
