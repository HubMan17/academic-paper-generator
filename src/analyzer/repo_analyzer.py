import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class Evidence:
    path: str
    lines: list[int] = field(default_factory=list)


@dataclass
class Language:
    name: str
    ratio: float
    lines_of_code: int
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class Framework:
    name: str
    type: str
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class Module:
    name: str
    role: str
    path: str
    submodules: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class APIEndpoint:
    method: str
    path: str
    full_path: str
    handler: str
    router: str
    file: str
    tags: list[str] = field(default_factory=list)
    auth_required: bool = False
    description: str = ""


@dataclass
class ORMModel:
    name: str
    table: str
    fields: list[dict]
    file: str
    relationships: list[dict] = field(default_factory=list)


@dataclass
class Feature:
    id: str
    summary: str
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class FrontendRoute:
    path: str
    name: str
    component: str
    file: str
    auth_required: bool = False


@dataclass
class Dependency:
    name: str
    version: str
    evidence: list[Evidence] = field(default_factory=list)


def normalize_path(path: str) -> str:
    return path.replace("\\", "/")


class RepoAnalyzer:
    FACTS_SCHEMA = "facts.v1"

    SKIP_DIRS = {
        "node_modules", "vendor", ".git", "__pycache__", "venv", ".venv",
        "env", "dist", "build", "eggs", ".eggs", ".tox", "htmlcov",
        ".next", ".nuxt", "coverage", ".cache", ".pytest_cache", ".mypy_cache"
    }

    EXTENSION_TO_LANG = {
        ".py": "Python",
        ".js": "JavaScript",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".jsx": "JavaScript",
        ".go": "Go",
        ".java": "Java",
        ".rs": "Rust",
        ".rb": "Ruby",
        ".php": "PHP",
        ".cs": "C#",
        ".cpp": "C++",
        ".c": "C",
        ".swift": "Swift",
        ".kt": "Kotlin",
        ".vue": "Vue",
        ".svelte": "Svelte",
    }

    PYTHON_FRAMEWORKS = {
        "django": ("Django", "web"),
        "fastapi": ("FastAPI", "web"),
        "flask": ("Flask", "web"),
        "celery": ("Celery", "task-queue"),
        "pytest": ("pytest", "testing"),
        "sqlalchemy": ("SQLAlchemy", "orm"),
        "pydantic": ("Pydantic", "validation"),
        "alembic": ("Alembic", "migrations"),
        "uvicorn": ("Uvicorn", "server"),
        "gunicorn": ("Gunicorn", "server"),
        "aiohttp": ("aiohttp", "web"),
        "starlette": ("Starlette", "web"),
    }

    JS_FRAMEWORKS = {
        "react": ("React", "frontend"),
        "vue": ("Vue.js", "frontend"),
        "angular": ("Angular", "frontend"),
        "svelte": ("Svelte", "frontend"),
        "next": ("Next.js", "fullstack"),
        "nuxt": ("Nuxt.js", "fullstack"),
        "express": ("Express", "backend"),
        "nestjs": ("NestJS", "backend"),
        "fastify": ("Fastify", "backend"),
        "tailwindcss": ("TailwindCSS", "styling"),
        "redux": ("Redux", "state-management"),
        "zustand": ("Zustand", "state-management"),
        "pinia": ("Pinia", "state-management"),
        "prisma": ("Prisma", "orm"),
        "typeorm": ("TypeORM", "orm"),
        "axios": ("Axios", "http-client"),
    }

    DEEP_ROLE_MAPPING = {
        "routers": "api-routing",
        "routes": "api-routing",
        "router": "routing",
        "controllers": "controllers",
        "models": "orm-models",
        "schemas": "data-schemas",
        "services": "business-logic",
        "repositories": "data-access",
        "utils": "utilities",
        "helpers": "utilities",
        "middleware": "middleware",
        "middlewares": "middleware",
        "auth": "authentication",
        "users": "user-management",
        "components": "ui-components",
        "pages": "pages",
        "views": "views",
        "stores": "state-management",
        "store": "state-management",
        "hooks": "react-hooks",
        "composables": "vue-composables",
        "api": "api-client",
        "config": "configuration",
        "constants": "constants",
        "types": "type-definitions",
        "interfaces": "type-definitions",
        "tests": "testing",
        "migrations": "migrations",
        "templates": "templates",
        "static": "static-files",
        "public": "static-files",
        "assets": "assets",
        "styles": "styles",
        "css": "styles",
    }

    def __init__(self, repo_url: str, work_dir: str | None = None):
        self.repo_url = repo_url
        self.work_dir = work_dir or tempfile.mkdtemp()
        self.repo_path: Path | None = None
        self.commit_sha: str | None = None

    def clone_repository(self) -> Path:
        result = subprocess.run(
            ["git", "ls-remote", self.repo_url],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"Repository not accessible: {result.stderr}")

        repo_name = self.repo_url.rstrip("/").split("/")[-1].replace(".git", "")
        self.repo_path = Path(self.work_dir) / repo_name

        result = subprocess.run(
            ["git", "clone", "--depth=1", self.repo_url, str(self.repo_path)],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"Clone failed: {result.stderr}")

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True
        )
        self.commit_sha = result.stdout.strip()

        return self.repo_path

    def _find_files_recursive(self, filename: str) -> list[Path]:
        if not self.repo_path:
            return []

        found = []
        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            if filename in files:
                found.append(Path(root) / filename)
        return found

    def _find_dirs_recursive(self, dirname: str) -> list[Path]:
        if not self.repo_path:
            return []

        found = []
        for root, dirs, _ in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            if dirname in dirs:
                found.append(Path(root) / dirname)
        return found

    def _count_lines(self, file_path: Path) -> int:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            lines = [l for l in content.splitlines() if l.strip() and not l.strip().startswith(("#", "//", "/*", "*"))]
            return len(lines)
        except Exception:
            return 0

    def _rel_path(self, path: Path) -> str:
        return normalize_path(str(path.relative_to(self.repo_path)))

    def detect_languages(self) -> list[Language]:
        if not self.repo_path:
            raise RuntimeError("Repository not cloned")

        lang_loc: dict[str, int] = {}

        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            for file in files:
                ext = Path(file).suffix.lower()
                if ext in self.EXTENSION_TO_LANG:
                    lang = self.EXTENSION_TO_LANG[ext]
                    file_path = Path(root) / file
                    loc = self._count_lines(file_path)
                    lang_loc[lang] = lang_loc.get(lang, 0) + loc

        total = sum(lang_loc.values())
        if total == 0:
            return []

        languages = []
        for lang, loc in sorted(lang_loc.items(), key=lambda x: -x[1]):
            ratio = round(loc / total, 2)
            extensions = [ext for ext, l in self.EXTENSION_TO_LANG.items() if l == lang]
            languages.append(Language(
                name=lang,
                ratio=ratio,
                lines_of_code=loc,
                evidence=[Evidence(path=f"*{ext}") for ext in extensions]
            ))

        return languages

    def _parse_requirements_txt(self, path: Path) -> list[Dependency]:
        deps = []
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("-"):
                    continue

                match = re.match(r'^([a-zA-Z0-9_-]+)\s*(\[.+\])?\s*([<>=!~]+.+)?', line)
                if match:
                    name = match.group(1).lower()
                    version = match.group(3) or "*"
                    rel_path = self._rel_path(path)
                    deps.append(Dependency(name=name, version=version.strip(), evidence=[Evidence(path=rel_path)]))
        except Exception:
            pass
        return deps

    def _parse_package_json(self, path: Path) -> tuple[list[Dependency], dict]:
        deps = []
        package_data = {}
        try:
            content = path.read_text(encoding="utf-8")
            package_data = json.loads(content)
            rel_path = self._rel_path(path)

            for dep_type in ["dependencies", "devDependencies"]:
                for name, version in package_data.get(dep_type, {}).items():
                    deps.append(Dependency(name=name.lower(), version=version, evidence=[Evidence(path=rel_path)]))
        except Exception:
            pass
        return deps, package_data

    def detect_frameworks(self) -> list[Framework]:
        if not self.repo_path:
            raise RuntimeError("Repository not cloned")

        frameworks = []
        found_frameworks = set()

        for req_path in self._find_files_recursive("requirements.txt"):
            deps = self._parse_requirements_txt(req_path)
            rel_path = self._rel_path(req_path)
            for dep in deps:
                if dep.name in self.PYTHON_FRAMEWORKS and dep.name not in found_frameworks:
                    name, fw_type = self.PYTHON_FRAMEWORKS[dep.name]
                    frameworks.append(Framework(name=name, type=fw_type, evidence=[Evidence(path=rel_path)]))
                    found_frameworks.add(dep.name)

        for pyproject_path in self._find_files_recursive("pyproject.toml"):
            content = pyproject_path.read_text(encoding="utf-8", errors="ignore").lower()
            rel_path = self._rel_path(pyproject_path)
            for key, (name, fw_type) in self.PYTHON_FRAMEWORKS.items():
                if key in content and key not in found_frameworks:
                    frameworks.append(Framework(name=name, type=fw_type, evidence=[Evidence(path=rel_path)]))
                    found_frameworks.add(key)

        for package_path in self._find_files_recursive("package.json"):
            deps, _ = self._parse_package_json(package_path)
            rel_path = self._rel_path(package_path)
            for dep in deps:
                for key, (name, fw_type) in self.JS_FRAMEWORKS.items():
                    if key in dep.name and key not in found_frameworks:
                        frameworks.append(Framework(name=name, type=fw_type, evidence=[Evidence(path=rel_path)]))
                        found_frameworks.add(key)

        return frameworks

    def detect_dependencies(self) -> list[Dependency]:
        if not self.repo_path:
            raise RuntimeError("Repository not cloned")

        all_deps = []
        seen = set()

        for req_path in self._find_files_recursive("requirements.txt"):
            for dep in self._parse_requirements_txt(req_path):
                if dep.name not in seen:
                    all_deps.append(dep)
                    seen.add(dep.name)

        for package_path in self._find_files_recursive("package.json"):
            deps, _ = self._parse_package_json(package_path)
            for dep in deps:
                if dep.name not in seen:
                    all_deps.append(dep)
                    seen.add(dep.name)

        return all_deps

    def extract_fastapi_routes(self) -> list[APIEndpoint]:
        if not self.repo_path:
            return []

        endpoints = []
        file_prefixes = {}
        global_prefix = ""

        router_prefix_pattern = re.compile(
            r'(?:router|\w+)\s*=\s*APIRouter\s*\([^)]*prefix\s*=\s*["\']([^"\']+)["\']'
        )
        include_pattern = re.compile(
            r'include_router\s*\(\s*(\w+)\s*(?:,\s*prefix\s*=\s*["\']([^"\']+)["\'])?'
        )
        import_alias_pattern = re.compile(
            r'from\s+\.(\w+)\s+import\s+router\s+as\s+(\w+)'
        )
        route_pattern = re.compile(
            r'@(?:app|router|\w+)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']([^)]*)\)'
        )
        handler_pattern = re.compile(
            r'@(?:app|router|\w+)\.(get|post|put|delete|patch)\s*\([^)]*\)\s*\n(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)'
        )
        router_tags_pattern = re.compile(
            r'APIRouter\s*\([^)]*tags\s*=\s*\[([^\]]+)\]'
        )

        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]

            for file in files:
                if not file.endswith(".py"):
                    continue

                file_path = Path(root) / file
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue

                rel_path = self._rel_path(file_path)

                for match in router_prefix_pattern.finditer(content):
                    prefix = match.group(1)
                    file_prefixes[rel_path] = prefix

        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]

            for file in files:
                if file != "main.py" and file != "app.py":
                    continue

                file_path = Path(root) / file
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue

                alias_map = {}
                for match in import_alias_pattern.finditer(content):
                    module_name = match.group(1)
                    alias = match.group(2)
                    alias_map[alias] = module_name

                for match in include_pattern.finditer(content):
                    router_alias = match.group(1)
                    api_prefix = match.group(2) or ""

                    module_name = alias_map.get(router_alias, router_alias.replace("_router", ""))

                    parent_path = Path(file_path).parent
                    possible_paths = [
                        f"{self._rel_path(parent_path)}/routers/{module_name}.py",
                        f"{self._rel_path(parent_path)}/{module_name}.py",
                        f"{self._rel_path(parent_path)}/routes/{module_name}.py",
                    ]

                    for pp in possible_paths:
                        if pp in file_prefixes:
                            combined = api_prefix.rstrip("/") + "/" + file_prefixes[pp].lstrip("/")
                            file_prefixes[pp] = "/" + combined.strip("/")
                            break
                    else:
                        for pp in possible_paths:
                            file_prefixes[pp] = api_prefix

                    if not global_prefix and api_prefix:
                        global_prefix = api_prefix

        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]

            for file in files:
                if not file.endswith(".py"):
                    continue

                file_path = Path(root) / file
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue

                rel_path = self._rel_path(file_path)

                current_router = "app"
                router_match = re.search(r'(\w+)\s*=\s*APIRouter', content)
                if router_match:
                    current_router = router_match.group(1)

                router_tags = []
                tags_match = router_tags_pattern.search(content)
                if tags_match:
                    raw_tags = tags_match.group(1)
                    router_tags = [t.strip().strip('"\'') for t in raw_tags.split(',')]

                prefix = file_prefixes.get(rel_path, "")

                if not prefix and ("routers/" in rel_path or "routes/" in rel_path):
                    dir_name = Path(rel_path).stem
                    if dir_name not in ["__init__", "main"]:
                        router_prefix_match = router_prefix_pattern.search(content)
                        if router_prefix_match:
                            prefix = global_prefix.rstrip("/") + router_prefix_match.group(1) if global_prefix else router_prefix_match.group(1)
                        else:
                            prefix = f"{global_prefix}/{dir_name}" if global_prefix else f"/{dir_name}"

                handlers = {}
                handler_params = {}
                for match in handler_pattern.finditer(content):
                    handler_name = match.group(2)
                    params = match.group(3)
                    start_pos = match.start()
                    handlers[start_pos] = handler_name
                    handler_params[handler_name] = params

                for match in route_pattern.finditer(content):
                    method = match.group(1).upper()
                    path = match.group(2)
                    decorator_args = match.group(3)
                    start_pos = match.start()

                    handler = "unknown"
                    for pos, name in handlers.items():
                        if pos >= start_pos and pos < start_pos + 300:
                            handler = name
                            break

                    tags = list(router_tags)
                    tags_in_route = re.search(r'tags\s*=\s*\[([^\]]+)\]', decorator_args)
                    if tags_in_route:
                        route_tags = [t.strip().strip('"\'') for t in tags_in_route.group(1).split(',')]
                        tags.extend(route_tags)

                    description = ""
                    desc_match = re.search(r'(?:summary|description)\s*=\s*["\']([^"\']+)["\']', decorator_args)
                    if desc_match:
                        description = desc_match.group(1)

                    auth_required = False
                    if handler in handler_params:
                        params = handler_params[handler]
                        if "Depends" in params and any(auth in params.lower() for auth in ["current_user", "auth", "token", "get_user"]):
                            auth_required = True

                    full_path = prefix.rstrip("/") + "/" + path.lstrip("/") if prefix else path
                    full_path = "/" + full_path.lstrip("/")

                    endpoints.append(APIEndpoint(
                        method=method,
                        path=path,
                        full_path=full_path,
                        handler=handler,
                        router=current_router,
                        file=rel_path,
                        tags=tags,
                        auth_required=auth_required,
                        description=description
                    ))

        return endpoints

    def _extract_column_type(self, type_str: str) -> str:
        depth = 0
        result = []
        for char in type_str:
            if char == '(':
                depth += 1
                result.append(char)
            elif char == ')':
                depth -= 1
                if depth >= 0:
                    result.append(char)
            elif char == ',' and depth == 0:
                break
            else:
                result.append(char)
        return ''.join(result).strip()

    def extract_orm_models(self) -> list[ORMModel]:
        if not self.repo_path:
            return []

        models = []
        skip_classes = {"Base", "Model", "DeclarativeBase"}

        sqlalchemy_class = re.compile(
            r'class\s+(\w+)\s*\([^)]*(?:Base|Model|DeclarativeBase)[^)]*\)\s*:'
        )
        tablename = re.compile(
            r'__tablename__\s*=\s*["\'](\w+)["\']'
        )
        column_pattern = re.compile(
            r'(\w+)\s*[=:]\s*(?:Column|Mapped)\s*[\[\(](.+?)(?:\n|$)'
        )
        relationship_pattern = re.compile(
            r'(\w+)\s*[=:]\s*relationship\s*\(\s*["\']?(\w+)["\']?'
        )
        foreign_key_pattern = re.compile(
            r'ForeignKey\s*\(\s*["\']([^"\']+)["\']'
        )

        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]

            for file in files:
                if not file.endswith(".py"):
                    continue

                file_path = Path(root) / file
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue

                if "sqlalchemy" not in content.lower() and "Column" not in content:
                    continue

                rel_path = self._rel_path(file_path)

                class_matches = list(sqlalchemy_class.finditer(content))
                for i, match in enumerate(class_matches):
                    class_name = match.group(1)

                    if class_name in skip_classes:
                        continue

                    start = match.end()
                    end = class_matches[i + 1].start() if i + 1 < len(class_matches) else len(content)
                    class_body = content[start:end]

                    table_match = tablename.search(class_body)
                    table_name = table_match.group(1) if table_match else class_name.lower() + "s"

                    fields = []
                    for col_match in column_pattern.finditer(class_body):
                        field_name = col_match.group(1)
                        if field_name in ["__tablename__", "__table_args__"]:
                            continue
                        raw_type = col_match.group(2)
                        field_type = self._extract_column_type(raw_type)

                        fk_match = foreign_key_pattern.search(raw_type)
                        field_info = {"name": field_name, "type": field_type}
                        if fk_match:
                            field_info["foreign_key"] = fk_match.group(1)
                        fields.append(field_info)

                    relationships = []
                    for rel_match in relationship_pattern.finditer(class_body):
                        rel_name = rel_match.group(1)
                        rel_target = rel_match.group(2)
                        relationships.append({"name": rel_name, "target": rel_target})

                    model = ORMModel(
                        name=class_name,
                        table=table_name,
                        fields=fields,
                        file=rel_path
                    )
                    if relationships:
                        model.relationships = relationships

                    models.append(model)

        return models

    def detect_architecture_type(self) -> dict[str, Any]:
        if not self.repo_path:
            raise RuntimeError("Repository not cloned")

        arch_type = "unknown"
        layers = []
        evidence = []
        details = {}

        has_frontend = False
        has_backend = False

        frontend_indicators = {"frontend", "client", "web", "ui"}
        backend_indicators = {"backend", "server", "api"}

        for item in self.repo_path.iterdir():
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

        frameworks = self.detect_frameworks()
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

        deps = self.detect_dependencies()
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
            for pyproject in self._find_files_recursive("pyproject.toml"):
                content = pyproject.read_text(encoding="utf-8", errors="ignore")
                if "[project]" in content or "[tool.poetry]" in content:
                    if "fastapi" not in content.lower() and "django" not in content.lower() and "flask" not in content.lower():
                        arch_type = "library"
                        break

        for dockerfile in self._find_files_recursive("Dockerfile"):
            if "infra" not in layers:
                layers.append("infra")
            evidence.append(Evidence(path=self._rel_path(dockerfile)))

        for compose in ["docker-compose.yml", "docker-compose.yaml"]:
            for found in self._find_files_recursive(compose):
                evidence.append(Evidence(path=self._rel_path(found)))

        return {
            "type": arch_type if arch_type != "unknown" else "monolith",
            "layers": list(set(layers)) if layers else ["unknown"],
            "details": details,
            "evidence": [{"path": e.path, "lines": e.lines} for e in evidence]
        }

    def extract_deep_modules(self) -> list[Module]:
        if not self.repo_path:
            raise RuntimeError("Repository not cloned")

        modules = []
        processed = set()

        top_level_dirs = ["backend", "frontend", "server", "client", "api", "web", "src", "app"]

        for tld in top_level_dirs:
            tld_path = self.repo_path / tld
            if not tld_path.exists() or not tld_path.is_dir():
                continue

            for item in tld_path.iterdir():
                if not item.is_dir():
                    continue
                if item.name.startswith((".", "_")) or item.name in self.SKIP_DIRS:
                    continue

                module_path = f"{tld}/{item.name}"
                if module_path in processed:
                    continue
                processed.add(module_path)

                role = self.DEEP_ROLE_MAPPING.get(item.name.lower(), "module")

                submodules = []
                for sub in item.iterdir():
                    if sub.is_dir() and not sub.name.startswith((".", "_")) and sub.name not in self.SKIP_DIRS:
                        sub_role = self.DEEP_ROLE_MAPPING.get(sub.name.lower(), "submodule")
                        submodules.append(f"{sub.name}:{sub_role}")

                modules.append(Module(
                    name=item.name,
                    role=role,
                    path=module_path,
                    submodules=submodules,
                    evidence=[Evidence(path=module_path)]
                ))

        for item in self.repo_path.iterdir():
            if not item.is_dir():
                continue
            if item.name.startswith((".", "_")) or item.name in self.SKIP_DIRS:
                continue
            if item.name.lower() in [t.lower() for t in top_level_dirs]:
                continue

            module_path = item.name
            if module_path in processed:
                continue
            processed.add(module_path)

            role = self.DEEP_ROLE_MAPPING.get(item.name.lower(), "top-level")

            modules.append(Module(
                name=item.name,
                role=role,
                path=module_path,
                submodules=[],
                evidence=[Evidence(path=module_path)]
            ))

        return modules

    def extract_features(self) -> list[Feature]:
        endpoints = self.extract_fastapi_routes()
        features = []
        seen = set()

        for ep in endpoints:
            feature_id = ep.full_path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
            if not feature_id:
                feature_id = "root"
            if feature_id in seen:
                continue
            seen.add(feature_id)

            features.append(Feature(
                id=feature_id,
                summary=f"Endpoint: {ep.full_path}",
                evidence=[Evidence(path=ep.file)]
            ))

        return features

    def extract_frontend_routes(self) -> list[FrontendRoute]:
        if not self.repo_path:
            return []

        routes = []

        vue_route_pattern = re.compile(
            r'\{\s*path\s*:\s*["\']([^"\']+)["\']'
            r'(?:[^}]*name\s*:\s*["\']([^"\']+)["\'])?'
            r'(?:[^}]*component\s*:\s*(?:(?:\(\)\s*=>\s*import\s*\(["\']([^"\']+)["\']\))|(\w+)))?'
            r'(?:[^}]*meta\s*:\s*\{[^}]*(?:requiresAuth|auth)\s*:\s*(true|false)[^}]*\})?'
        )
        react_route_pattern = re.compile(
            r'<Route[^>]*path\s*=\s*["\']([^"\']+)["\'][^>]*(?:element\s*=\s*\{?\s*<\s*(\w+)|component\s*=\s*\{?\s*(\w+))?'
        )

        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]

            for file in files:
                if not file.endswith((".ts", ".tsx", ".js", ".jsx", ".vue")):
                    continue

                file_path = Path(root) / file
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue

                if "router" not in file.lower() and "route" not in content.lower():
                    continue

                rel_path = self._rel_path(file_path)

                for match in vue_route_pattern.finditer(content):
                    path = match.group(1)
                    name = match.group(2) or ""
                    component = match.group(3) or match.group(4) or ""
                    auth_str = match.group(5)
                    auth_required = auth_str == "true" if auth_str else False

                    if component:
                        component = component.split("/")[-1].replace(".vue", "").replace(".tsx", "").replace(".ts", "")

                    routes.append(FrontendRoute(
                        path=path,
                        name=name,
                        component=component,
                        file=rel_path,
                        auth_required=auth_required
                    ))

                for match in react_route_pattern.finditer(content):
                    path = match.group(1)
                    component = match.group(2) or match.group(3) or ""

                    routes.append(FrontendRoute(
                        path=path,
                        name="",
                        component=component,
                        file=rel_path,
                        auth_required=False
                    ))

        return routes

    def extract_modules(self) -> list[Module]:
        if not self.repo_path:
            raise RuntimeError("Repository not cloned")

        modules = []

        for item in self.repo_path.iterdir():
            if not item.is_dir():
                continue
            if item.name.startswith((".", "_")) or item.name in self.SKIP_DIRS:
                continue

            role = self.DEEP_ROLE_MAPPING.get(item.name.lower(), "module")
            if item.name.lower() in ["backend", "server", "api"]:
                role = "backend"
            elif item.name.lower() in ["frontend", "client", "web", "ui"]:
                role = "frontend"

            modules.append(Module(
                name=item.name,
                role=role,
                path=item.name,
                submodules=[],
                evidence=[Evidence(path=item.name)]
            ))

        return modules

    def _find_build_files(self) -> list[str]:
        if not self.repo_path:
            return []

        build_files = []
        candidates = [
            "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
            "Makefile", "setup.py", "pyproject.toml", "setup.cfg",
            "package.json", "tsconfig.json", "vite.config.js", "vite.config.ts",
            "webpack.config.js", "next.config.js", "nuxt.config.js", "nuxt.config.ts"
        ]

        for candidate in candidates:
            found = self._find_files_recursive(candidate)
            for f in found:
                rel_path = self._rel_path(f)
                if rel_path not in build_files:
                    build_files.append(rel_path)

        return build_files

    def _find_entrypoints(self) -> list[str]:
        if not self.repo_path:
            return []

        entrypoints = []
        candidates = [
            "main.py", "app.py", "manage.py", "wsgi.py", "asgi.py",
            "index.js", "app.js", "server.js", "main.go", "main.rs",
            "index.ts", "main.ts"
        ]

        for candidate in candidates:
            found = self._find_files_recursive(candidate)
            for f in found:
                rel_path = self._rel_path(f)
                if rel_path not in entrypoints:
                    entrypoints.append(rel_path)

        return entrypoints

    def generate_facts_json(self) -> dict[str, Any]:
        languages = self.detect_languages()
        frameworks = self.detect_frameworks()
        architecture = self.detect_architecture_type()
        modules = self.extract_deep_modules()
        endpoints = self.extract_fastapi_routes()
        frontend_routes = self.extract_frontend_routes()
        orm_models = self.extract_orm_models()
        dependencies = self.detect_dependencies()

        return {
            "schema": self.FACTS_SCHEMA,
            "repo": {
                "url": self.repo_url,
                "commit": self.commit_sha,
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
                "build_files": self._find_build_files(),
                "entrypoints": self._find_entrypoints()
            }
        }

    def analyze(self) -> dict[str, Any]:
        self.clone_repository()
        return self.generate_facts_json()

    def save_facts(self, output_path: str | Path) -> None:
        facts = self.generate_facts_json()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(facts, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python repo_analyzer.py <repo_url> [output_path]")
        sys.exit(1)

    repo_url = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "facts.json"

    analyzer = RepoAnalyzer(repo_url)
    try:
        facts = analyzer.analyze()
        analyzer.save_facts(output_path)
        print(f"Facts saved to {output_path}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
