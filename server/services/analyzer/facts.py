from datetime import datetime
from pathlib import Path
from typing import Any

from .constants import FACTS_SCHEMA
from .detectors import detect_languages, detect_frameworks, detect_dependencies, detect_architecture_type
from .extractors import extract_fastapi_routes, extract_orm_models, extract_frontend_routes, extract_deep_modules
from .utils import find_files_recursive, rel_path


def find_build_files(repo_path: Path) -> list[str]:
    if not repo_path:
        return []

    build_files = []
    candidates = [
        "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
        "Makefile", "setup.py", "pyproject.toml", "setup.cfg",
        "package.json", "tsconfig.json", "vite.config.js", "vite.config.ts",
        "webpack.config.js", "next.config.js", "nuxt.config.js", "nuxt.config.ts"
    ]

    for candidate in candidates:
        found = find_files_recursive(repo_path, candidate)
        for f in found:
            rel_path_str = rel_path(f, repo_path)
            if rel_path_str not in build_files:
                build_files.append(rel_path_str)

    return build_files


def find_entrypoints(repo_path: Path) -> list[str]:
    if not repo_path:
        return []

    entrypoints = []
    candidates = [
        "main.py", "app.py", "manage.py", "wsgi.py", "asgi.py",
        "index.js", "app.js", "server.js", "main.go", "main.rs",
        "index.ts", "main.ts"
    ]

    for candidate in candidates:
        found = find_files_recursive(repo_path, candidate)
        for f in found:
            rel_path_str = rel_path(f, repo_path)
            if rel_path_str not in entrypoints:
                entrypoints.append(rel_path_str)

    return entrypoints


def generate_facts_json(repo_path: Path, repo_url: str, commit_sha: str) -> dict[str, Any]:
    languages = detect_languages(repo_path)
    frameworks = detect_frameworks(repo_path)
    architecture = detect_architecture_type(repo_path)
    modules = extract_deep_modules(repo_path)
    endpoints = extract_fastapi_routes(repo_path)
    frontend_routes = extract_frontend_routes(repo_path)
    orm_models = extract_orm_models(repo_path)
    dependencies = detect_dependencies(repo_path)

    return {
        "schema": FACTS_SCHEMA,
        "repo": {
            "url": repo_url,
            "commit": commit_sha,
            "detected_at": datetime.utcnow().isoformat() + "Z"
        },
        "languages": [
            {
                "name": lang.name,
                "ratio": lang.ratio,
                "lines_of_code": lang.lines_of_code,
                "evidence": [{"path": e.path} for e in lang.evidence]
            }
            for lang in languages
        ],
        "frameworks": [
            {
                "name": fw.name,
                "type": fw.type,
                "evidence": [{"path": e.path} for e in fw.evidence]
            }
            for fw in frameworks
        ],
        "architecture": architecture,
        "modules": [
            {
                "name": mod.name,
                "role": mod.role,
                "path": mod.path,
                "submodules": mod.submodules,
                "evidence": [{"path": e.path} for e in mod.evidence]
            }
            for mod in modules
        ],
        "api": {
            "endpoints": [
                {
                    "method": ep.method,
                    "path": ep.path,
                    "full_path": ep.full_path,
                    "handler": ep.handler,
                    "router": ep.router,
                    "file": ep.file,
                    "tags": ep.tags,
                    "auth_required": ep.auth_required,
                    "description": ep.description
                }
                for ep in endpoints
            ],
            "total_count": len(endpoints)
        },
        "frontend_routes": [
            {
                "path": route.path,
                "name": route.name,
                "component": route.component,
                "file": route.file,
                "auth_required": route.auth_required
            }
            for route in frontend_routes
        ],
        "models": [
            {
                "name": model.name,
                "table": model.table,
                "fields": model.fields,
                "relationships": model.relationships,
                "file": model.file
            }
            for model in orm_models
        ],
        "runtime": {
            "dependencies": [
                {
                    "name": dep.name,
                    "version": dep.version,
                    "evidence": [{"path": e.path} for e in dep.evidence]
                }
                for dep in dependencies
            ],
            "build_files": find_build_files(repo_path),
            "entrypoints": find_entrypoints(repo_path)
        }
    }
