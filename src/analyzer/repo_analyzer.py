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
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class Feature:
    id: str
    summary: str
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class Dependency:
    name: str
    version: str
    evidence: list[Evidence] = field(default_factory=list)


class RepoAnalyzer:
    FACTS_SCHEMA = "facts.v1"

    SKIP_DIRS = {
        "node_modules", "vendor", ".git", "__pycache__", "venv", ".venv",
        "env", "dist", "build", "eggs", ".eggs", ".tox", "htmlcov",
        ".next", ".nuxt", "coverage", ".cache", ".pytest_cache"
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
        "tornado": ("Tornado", "web"),
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
        "koa": ("Koa", "backend"),
        "hapi": ("Hapi", "backend"),
        "tailwindcss": ("TailwindCSS", "styling"),
        "redux": ("Redux", "state-management"),
        "zustand": ("Zustand", "state-management"),
        "prisma": ("Prisma", "orm"),
        "typeorm": ("TypeORM", "orm"),
        "mongoose": ("Mongoose", "odm"),
    }

    ROLE_MAPPING = {
        "auth": "authentication",
        "users": "user-management",
        "billing": "payments",
        "payments": "payments",
        "core": "core-logic",
        "domain": "domain-logic",
        "infra": "infrastructure",
        "api": "api-layer",
        "services": "business-logic",
        "models": "data-models",
        "utils": "utilities",
        "common": "shared-code",
        "frontend": "frontend",
        "backend": "backend",
        "client": "frontend",
        "server": "backend",
        "web": "frontend",
        "lib": "library",
        "libs": "library",
        "packages": "library",
        "components": "ui-components",
        "hooks": "react-hooks",
        "pages": "pages",
        "views": "views",
        "routes": "routing",
        "routers": "routing",
        "controllers": "controllers",
        "middlewares": "middleware",
        "middleware": "middleware",
        "schemas": "data-schemas",
        "tests": "testing",
        "test": "testing",
        "config": "configuration",
        "configs": "configuration",
        "migrations": "migrations",
        "static": "static-files",
        "public": "static-files",
        "assets": "assets",
        "templates": "templates",
        "docs": "documentation",
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

    def _should_skip_dir(self, path: str) -> bool:
        parts = Path(path).parts
        return any(part in self.SKIP_DIRS for part in parts)

    def _find_files_recursive(self, filename: str) -> list[Path]:
        if not self.repo_path:
            return []

        found = []
        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            if filename in files:
                found.append(Path(root) / filename)
        return found

    def detect_languages(self) -> list[Language]:
        if not self.repo_path:
            raise RuntimeError("Repository not cloned")

        extension_counts: dict[str, int] = {}

        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            for file in files:
                ext = Path(file).suffix.lower()
                if ext in self.EXTENSION_TO_LANG:
                    lang = self.EXTENSION_TO_LANG[ext]
                    extension_counts[lang] = extension_counts.get(lang, 0) + 1

        total = sum(extension_counts.values())
        if total == 0:
            return []

        languages = []
        for lang, count in sorted(extension_counts.items(), key=lambda x: -x[1]):
            ratio = round(count / total, 2)
            extensions = [ext for ext, l in self.EXTENSION_TO_LANG.items() if l == lang]
            languages.append(Language(
                name=lang,
                ratio=ratio,
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

                match = re.match(r'^([a-zA-Z0-9_-]+)\s*([<>=!~]+.+)?', line)
                if match:
                    name = match.group(1).lower()
                    version = match.group(2) or "*"
                    rel_path = str(path.relative_to(self.repo_path))
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
            rel_path = str(path.relative_to(self.repo_path))

            for dep_type in ["dependencies", "devDependencies"]:
                for name, version in package_data.get(dep_type, {}).items():
                    deps.append(Dependency(name=name.lower(), version=version, evidence=[Evidence(path=rel_path)]))
        except Exception:
            pass
        return deps, package_data

    def _parse_pyproject_toml(self, path: Path) -> list[Dependency]:
        deps = []
        try:
            content = path.read_text(encoding="utf-8")
            rel_path = str(path.relative_to(self.repo_path))

            in_deps = False
            for line in content.splitlines():
                if "[project.dependencies]" in line or "[tool.poetry.dependencies]" in line:
                    in_deps = True
                    continue
                if in_deps and line.startswith("["):
                    in_deps = False
                if in_deps and "=" in line:
                    match = re.match(r'^([a-zA-Z0-9_-]+)\s*=', line)
                    if match:
                        deps.append(Dependency(name=match.group(1).lower(), version="*", evidence=[Evidence(path=rel_path)]))

                dep_match = re.findall(r'"([a-zA-Z0-9_-]+)(?:[<>=!~].+)?"', line)
                for dep_name in dep_match:
                    if dep_name.lower() not in [d.name for d in deps]:
                        deps.append(Dependency(name=dep_name.lower(), version="*", evidence=[Evidence(path=rel_path)]))
        except Exception:
            pass
        return deps

    def detect_frameworks(self) -> list[Framework]:
        if not self.repo_path:
            raise RuntimeError("Repository not cloned")

        frameworks = []
        found_frameworks = set()

        for req_path in self._find_files_recursive("requirements.txt"):
            deps = self._parse_requirements_txt(req_path)
            rel_path = str(req_path.relative_to(self.repo_path))
            for dep in deps:
                if dep.name in self.PYTHON_FRAMEWORKS and dep.name not in found_frameworks:
                    name, fw_type = self.PYTHON_FRAMEWORKS[dep.name]
                    frameworks.append(Framework(name=name, type=fw_type, evidence=[Evidence(path=rel_path)]))
                    found_frameworks.add(dep.name)

        for pyproject_path in self._find_files_recursive("pyproject.toml"):
            content = pyproject_path.read_text(encoding="utf-8", errors="ignore").lower()
            rel_path = str(pyproject_path.relative_to(self.repo_path))
            for key, (name, fw_type) in self.PYTHON_FRAMEWORKS.items():
                if key in content and key not in found_frameworks:
                    frameworks.append(Framework(name=name, type=fw_type, evidence=[Evidence(path=rel_path)]))
                    found_frameworks.add(key)

        for package_path in self._find_files_recursive("package.json"):
            deps, _ = self._parse_package_json(package_path)
            rel_path = str(package_path.relative_to(self.repo_path))
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

        for pyproject_path in self._find_files_recursive("pyproject.toml"):
            for dep in self._parse_pyproject_toml(pyproject_path):
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

    def detect_architecture_type(self) -> dict[str, Any]:
        if not self.repo_path:
            raise RuntimeError("Repository not cloned")

        arch_type = "unknown"
        layers = []
        evidence = []

        has_frontend = False
        has_backend = False

        frontend_dirs = {"frontend", "client", "web", "ui", "app"}
        backend_dirs = {"backend", "server", "api"}

        for item in self.repo_path.iterdir():
            if item.is_dir():
                name_lower = item.name.lower()
                if name_lower in frontend_dirs:
                    has_frontend = True
                    layers.append("frontend")
                    evidence.append(Evidence(path=item.name))
                if name_lower in backend_dirs:
                    has_backend = True
                    layers.append("backend")
                    evidence.append(Evidence(path=item.name))

        if has_frontend and has_backend:
            arch_type = "client-server"
        elif has_frontend:
            arch_type = "web"
            layers.append("frontend")
        elif has_backend:
            arch_type = "api"
            layers.append("backend")

        frameworks = self.detect_frameworks()
        for fw in frameworks:
            if fw.type == "fullstack":
                arch_type = "fullstack"
                if "frontend" not in layers:
                    layers.append("frontend")
                if "backend" not in layers:
                    layers.append("backend")
            elif fw.type == "frontend" and "frontend" not in layers:
                layers.append("frontend")
                if arch_type == "unknown":
                    arch_type = "web"
            elif fw.type in ("web", "backend") and "backend" not in layers:
                layers.append("backend")
                if arch_type == "unknown":
                    arch_type = "api"

        if arch_type == "unknown":
            web_indicators = ["routes", "controllers", "views", "api", "endpoints", "routers"]
            for indicator in web_indicators:
                for found in self._find_files_recursive(indicator):
                    if found.is_dir():
                        arch_type = "web"
                        layers.append("api")
                        evidence.append(Evidence(path=str(found.relative_to(self.repo_path))))
                        break

        if arch_type == "unknown":
            desktop_extensions = [".ui", ".qml", ".xib", ".xaml"]
            for root, dirs, files in os.walk(self.repo_path):
                dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
                for file in files:
                    if any(file.endswith(ext) for ext in desktop_extensions):
                        arch_type = "desktop"
                        evidence.append(Evidence(path=file))
                        break
                if arch_type == "desktop":
                    break

        if arch_type == "unknown":
            pyproject_files = self._find_files_recursive("pyproject.toml")
            setup_files = self._find_files_recursive("setup.py")
            if pyproject_files or setup_files:
                for pp in pyproject_files:
                    content = pp.read_text(encoding="utf-8", errors="ignore")
                    if "[project]" in content or "[tool.poetry]" in content:
                        if "console_scripts" not in content and "gui_scripts" not in content:
                            arch_type = "library"
                            evidence.append(Evidence(path=str(pp.relative_to(self.repo_path))))

        if arch_type == "unknown":
            cli_indicators = ["cli.py", "__main__.py"]
            for indicator in cli_indicators:
                found = self._find_files_recursive(indicator)
                if found:
                    arch_type = "cli"
                    evidence.append(Evidence(path=str(found[0].relative_to(self.repo_path))))
                    break

        for dockerfile in self._find_files_recursive("Dockerfile"):
            layers.append("infra")
            evidence.append(Evidence(path=str(dockerfile.relative_to(self.repo_path))))

        for compose in ["docker-compose.yml", "docker-compose.yaml"]:
            for found in self._find_files_recursive(compose):
                evidence.append(Evidence(path=str(found.relative_to(self.repo_path))))

        return {
            "type": arch_type,
            "layers": list(set(layers)) if layers else ["unknown"],
            "evidence": [{"path": e.path, "lines": e.lines} for e in evidence]
        }

    def extract_modules(self) -> list[Module]:
        if not self.repo_path:
            raise RuntimeError("Repository not cloned")

        modules = []
        found_modules = set()

        search_dirs = [
            self.repo_path / "src",
            self.repo_path / "app",
            self.repo_path,
        ]

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue

            for item in search_dir.iterdir():
                if not item.is_dir():
                    continue
                if item.name.startswith((".", "_")):
                    continue
                if item.name in self.SKIP_DIRS:
                    continue
                if item.name in found_modules:
                    continue

                role = self.ROLE_MAPPING.get(item.name.lower(), "module")
                modules.append(Module(
                    name=item.name,
                    role=role,
                    evidence=[Evidence(path=str(item.relative_to(self.repo_path)))]
                ))
                found_modules.add(item.name)

        return modules

    def extract_features(self) -> list[Feature]:
        if not self.repo_path:
            raise RuntimeError("Repository not cloned")

        features = []
        seen_features = set()

        route_patterns = [
            (r'@app\.(?:get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']', "FastAPI/Flask route"),
            (r'@router\.(?:get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']', "FastAPI router"),
            (r'path\s*\(\s*["\']([^"\']+)["\']', "Django path"),
            (r'url\s*\(\s*r?["\']([^"\']+)["\']', "Django url"),
            (r'app\.(?:get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']', "Express route"),
            (r'router\.(?:get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']', "Express router"),
            (r'@(?:Get|Post|Put|Delete|Patch)\s*\(\s*["\']([^"\']+)["\']', "NestJS route"),
        ]

        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]

            for file in files:
                if not file.endswith((".py", ".js", ".ts")):
                    continue

                file_path = Path(root) / file
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue

                for pattern, route_type in route_patterns:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        route = match.strip()
                        if route and route not in seen_features:
                            feature_id = self._route_to_feature_id(route)
                            rel_path = str(file_path.relative_to(self.repo_path))
                            features.append(Feature(
                                id=feature_id,
                                summary=f"Endpoint: {route}",
                                evidence=[Evidence(path=rel_path)]
                            ))
                            seen_features.add(route)

        return features

    def _route_to_feature_id(self, route: str) -> str:
        clean = re.sub(r'[{}<>:*?]', '', route)
        clean = clean.strip('/').replace('/', '_').replace('-', '_')
        return clean or "root"

    def _find_build_files(self) -> list[str]:
        if not self.repo_path:
            return []

        build_files = []
        candidates = [
            "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
            "Makefile", "setup.py", "pyproject.toml", "setup.cfg",
            "tox.ini", "noxfile.py", "justfile", "package.json",
            "tsconfig.json", "webpack.config.js", "vite.config.js",
            "vite.config.ts", "next.config.js", "nuxt.config.js"
        ]

        for candidate in candidates:
            found = self._find_files_recursive(candidate)
            for f in found:
                rel_path = str(f.relative_to(self.repo_path))
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
            "index.ts", "main.ts", "__main__.py"
        ]

        for candidate in candidates:
            found = self._find_files_recursive(candidate)
            for f in found:
                rel_path = str(f.relative_to(self.repo_path))
                if rel_path not in entrypoints:
                    entrypoints.append(rel_path)

        return entrypoints

    def generate_facts_json(self) -> dict[str, Any]:
        languages = self.detect_languages()
        frameworks = self.detect_frameworks()
        architecture = self.detect_architecture_type()
        modules = self.extract_modules()
        features = self.extract_features()
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
                    "evidence": [{"path": e.path} for e in mod.evidence]
                }
                for mod in modules
            ],
            "features": [
                {
                    "id": feat.id,
                    "summary": feat.summary,
                    "evidence": [{"path": e.path} for e in feat.evidence]
                }
                for feat in features
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
