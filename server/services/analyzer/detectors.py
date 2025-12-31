import os
from pathlib import Path
from typing import Any

from .constants import (
    EXTENSION_TO_LANG, PYTHON_FRAMEWORKS, JS_FRAMEWORKS, SKIP_DIRS, DEEP_ROLE_MAPPING
)
from .models import Language, Framework, Dependency, Evidence
from .parsers import parse_requirements_txt, parse_package_json
from .utils import rel_path, find_files_recursive, count_lines


def detect_languages(repo_path: Path) -> list[Language]:
    if not repo_path:
        raise RuntimeError("Repository not cloned")

    lang_loc: dict[str, int] = {}

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for file in files:
            ext = Path(file).suffix.lower()
            if ext in EXTENSION_TO_LANG:
                lang = EXTENSION_TO_LANG[ext]
                file_path = Path(root) / file
                loc = count_lines(file_path)
                lang_loc[lang] = lang_loc.get(lang, 0) + loc

    total = sum(lang_loc.values())
    if total == 0:
        return []

    languages = []
    for lang, loc in sorted(lang_loc.items(), key=lambda x: -x[1]):
        ratio = round(loc / total, 2)
        extensions = [ext for ext, l in EXTENSION_TO_LANG.items() if l == lang]
        languages.append(Language(
            name=lang,
            ratio=ratio,
            lines_of_code=loc,
            evidence=[Evidence(path=f"*{ext}") for ext in extensions]
        ))

    return languages


def detect_frameworks(repo_path: Path) -> list[Framework]:
    if not repo_path:
        raise RuntimeError("Repository not cloned")

    frameworks = []
    found_frameworks = set()

    for req_path in find_files_recursive(repo_path, "requirements.txt"):
        rel_path_str = rel_path(req_path, repo_path)
        deps = parse_requirements_txt(req_path, rel_path_str)
        for dep in deps:
            if dep.name in PYTHON_FRAMEWORKS and dep.name not in found_frameworks:
                name, fw_type = PYTHON_FRAMEWORKS[dep.name]
                frameworks.append(Framework(
                    name=name,
                    type=fw_type,
                    evidence=[Evidence(path=rel_path_str)]
                ))
                found_frameworks.add(dep.name)

    for pyproject_path in find_files_recursive(repo_path, "pyproject.toml"):
        content = pyproject_path.read_text(encoding="utf-8", errors="ignore").lower()
        rel_path_str = rel_path(pyproject_path, repo_path)
        for key, (name, fw_type) in PYTHON_FRAMEWORKS.items():
            if key in content and key not in found_frameworks:
                frameworks.append(Framework(
                    name=name,
                    type=fw_type,
                    evidence=[Evidence(path=rel_path_str)]
                ))
                found_frameworks.add(key)

    for package_path in find_files_recursive(repo_path, "package.json"):
        rel_path_str = rel_path(package_path, repo_path)
        deps, _ = parse_package_json(package_path, rel_path_str)
        for dep in deps:
            for key, (name, fw_type) in JS_FRAMEWORKS.items():
                if key in dep.name and key not in found_frameworks:
                    frameworks.append(Framework(
                        name=name,
                        type=fw_type,
                        evidence=[Evidence(path=rel_path_str)]
                    ))
                    found_frameworks.add(key)

    return frameworks


def detect_dependencies(repo_path: Path) -> list[Dependency]:
    if not repo_path:
        raise RuntimeError("Repository not cloned")

    all_deps = []
    seen = set()

    for req_path in find_files_recursive(repo_path, "requirements.txt"):
        rel_path_str = rel_path(req_path, repo_path)
        for dep in parse_requirements_txt(req_path, rel_path_str):
            if dep.name not in seen:
                all_deps.append(dep)
                seen.add(dep.name)

    for package_path in find_files_recursive(repo_path, "package.json"):
        rel_path_str = rel_path(package_path, repo_path)
        deps, _ = parse_package_json(package_path, rel_path_str)
        for dep in deps:
            if dep.name not in seen:
                all_deps.append(dep)
                seen.add(dep.name)

    return all_deps


def detect_architecture_type(repo_path: Path) -> dict[str, Any]:
    if not repo_path:
        raise RuntimeError("Repository not cloned")

    arch_type = "unknown"
    layers = []
    evidence = []
    details = {}

    has_frontend = False
    has_backend = False

    frontend_indicators = {"frontend", "client", "web", "ui"}
    backend_indicators = {"backend", "server", "api"}

    for item in repo_path.iterdir():
        if item.is_dir():
            name_lower = item.name.lower()
            if name_lower in frontend_indicators:
                has_frontend = True
                layers.append("frontend")
                evidence.append(Evidence(path=item.name))
            if name_lower in backend_indicators:
                has_backend = True
                layers.append("backend")
                evidence.append(Evidence(path=item.name))

    if has_frontend and has_backend:
        arch_type = "client-server"
        details["separation"] = "monorepo"
    elif has_frontend:
        arch_type = "spa"
    elif has_backend:
        arch_type = "api"

    frameworks = detect_frameworks(repo_path)
    fw_names = {fw.name.lower() for fw in frameworks}

    if "next.js" in fw_names or "nuxt.js" in fw_names:
        arch_type = "fullstack-ssr"

    if any(name in fw_names for name in ["fastapi", "flask", "django", "express", "nestjs"]):
        details["api_type"] = "REST"
        if "backend" not in layers:
            layers.append("backend")
        if arch_type == "unknown":
            arch_type = "api"

    if any(name in fw_names for name in ["react", "vue.js", "angular", "svelte"]):
        if "frontend" not in layers:
            layers.append("frontend")
        if arch_type == "unknown":
            arch_type = "spa"

    deps = detect_dependencies(repo_path)
    dep_dict = {d.name: d for d in deps}
    dep_names = set(dep_dict.keys())

    db_frameworks = []
    for name in ["sqlalchemy", "prisma", "typeorm"]:
        if name in fw_names:
            db_frameworks.append(name)
    if db_frameworks:
        db_deps = ["aiosqlite", "psycopg2", "asyncpg", "mysql-connector", "pymongo"]
        db_type = "relational"
        db_evidence = []
        for dep_name in db_deps:
            if dep_name in dep_names:
                db_evidence.append(dep_dict[dep_name].evidence[0].path if dep_dict[dep_name].evidence else dep_name)
        for fw in frameworks:
            if fw.name.lower() in db_frameworks:
                db_evidence.append(fw.evidence[0].path if fw.evidence else fw.name)
        details["database"] = {"type": db_type, "orm": db_frameworks[0].title(), "evidence": db_evidence}
        if "data" not in layers:
            layers.append("data")

    jwt_deps = ["python-jose", "pyjwt", "jsonwebtoken"]
    for jwt_dep in jwt_deps:
        if jwt_dep in dep_names:
            details["auth"] = {
                "type": "JWT",
                "library": jwt_dep,
                "evidence": [dep_dict[jwt_dep].evidence[0].path] if dep_dict[jwt_dep].evidence else [jwt_dep]
            }
            break

    if "axios" in dep_names:
        details["http_client"] = {"name": "axios", "evidence": [dep_dict["axios"].evidence[0].path] if dep_dict["axios"].evidence else ["axios"]}
    elif "fetch" in dep_names:
        details["http_client"] = {"name": "fetch", "evidence": ["native"]}

    state_libs = [("pinia", "Pinia"), ("redux", "Redux"), ("zustand", "Zustand")]
    for lib_name, lib_display in state_libs:
        if lib_name in dep_names:
            details["state_management"] = {
                "name": lib_display,
                "evidence": [dep_dict[lib_name].evidence[0].path] if dep_dict[lib_name].evidence else [lib_name]
            }
            break

    if arch_type == "unknown":
        for pyproject in find_files_recursive(repo_path, "pyproject.toml"):
            content = pyproject.read_text(encoding="utf-8", errors="ignore")
            if "[project]" in content or "[tool.poetry]" in content:
                if "fastapi" not in content.lower() and "django" not in content.lower() and "flask" not in content.lower():
                    arch_type = "library"
                    break

    for dockerfile in find_files_recursive(repo_path, "Dockerfile"):
        if "infra" not in layers:
            layers.append("infra")
        evidence.append(Evidence(path=rel_path(dockerfile, repo_path)))

    for compose in ["docker-compose.yml", "docker-compose.yaml"]:
        for found in find_files_recursive(repo_path, compose):
            evidence.append(Evidence(path=rel_path(found, repo_path)))

    return {
        "type": arch_type if arch_type != "unknown" else "monolith",
        "layers": list(set(layers)) if layers else ["unknown"],
        "details": details,
        "evidence": [{"path": e.path, "lines": e.lines} for e in evidence]
    }
