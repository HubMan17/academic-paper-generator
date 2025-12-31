import json
import os
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


class RepoAnalyzer:
    FACTS_SCHEMA = "facts.v1"

    TEMPLATE_PATTERNS = [
        "README-template*",
        "TEMPLATE*",
        ".github/ISSUE_TEMPLATE*",
        ".github/PULL_REQUEST_TEMPLATE*",
    ]

    DEPENDENCY_FILES = {
        "python": ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"],
        "javascript": ["package.json", "package-lock.json", "yarn.lock"],
        "go": ["go.mod", "go.sum"],
        "java": ["pom.xml", "build.gradle"],
        "rust": ["Cargo.toml"],
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

    def detect_languages(self) -> list[Language]:
        if not self.repo_path:
            raise RuntimeError("Repository not cloned")

        extension_counts: dict[str, int] = {}

        for root, _, files in os.walk(self.repo_path):
            if ".git" in root or "vendor" in root or "node_modules" in root:
                continue
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

    def detect_frameworks(self) -> list[Framework]:
        if not self.repo_path:
            raise RuntimeError("Repository not cloned")

        frameworks = []
        found_frameworks = set()

        python_frameworks = {
            "django": ("Django", "web"),
            "fastapi": ("FastAPI", "web"),
            "flask": ("Flask", "web"),
            "celery": ("Celery", "task-queue"),
            "pytest": ("pytest", "testing"),
            "sqlalchemy": ("SQLAlchemy", "orm"),
            "pydantic": ("Pydantic", "validation"),
        }

        js_frameworks = {
            "react": ("React", "frontend"),
            "vue": ("Vue.js", "frontend"),
            "angular": ("Angular", "frontend"),
            "next": ("Next.js", "fullstack"),
            "nuxt": ("Nuxt.js", "fullstack"),
            "express": ("Express", "backend"),
            "nestjs": ("NestJS", "backend"),
            "fastify": ("Fastify", "backend"),
        }

        requirements_path = self.repo_path / "requirements.txt"
        if requirements_path.exists():
            content = requirements_path.read_text().lower()
            for key, (name, fw_type) in python_frameworks.items():
                if key in content and name not in found_frameworks:
                    frameworks.append(Framework(
                        name=name,
                        type=fw_type,
                        evidence=[Evidence(path="requirements.txt")]
                    ))
                    found_frameworks.add(name)

        pyproject_path = self.repo_path / "pyproject.toml"
        if pyproject_path.exists():
            content = pyproject_path.read_text().lower()
            for key, (name, fw_type) in python_frameworks.items():
                if key in content and name not in found_frameworks:
                    frameworks.append(Framework(
                        name=name,
                        type=fw_type,
                        evidence=[Evidence(path="pyproject.toml")]
                    ))
                    found_frameworks.add(name)

        package_json_path = self.repo_path / "package.json"
        if package_json_path.exists():
            try:
                with open(package_json_path) as f:
                    package_data = json.load(f)
                deps = {
                    **package_data.get("dependencies", {}),
                    **package_data.get("devDependencies", {})
                }
                for key, (name, fw_type) in js_frameworks.items():
                    if any(key in dep.lower() for dep in deps.keys()):
                        if name not in found_frameworks:
                            frameworks.append(Framework(
                                name=name,
                                type=fw_type,
                                evidence=[Evidence(path="package.json")]
                            ))
                            found_frameworks.add(name)
            except json.JSONDecodeError:
                pass

        return frameworks

    def detect_architecture_type(self) -> dict[str, Any]:
        if not self.repo_path:
            raise RuntimeError("Repository not cloned")

        arch_type = "unknown"
        layers = []
        evidence = []

        web_indicators = ["routes", "controllers", "views", "api", "endpoints", "routers"]
        for indicator in web_indicators:
            indicator_path = self.repo_path / indicator
            if indicator_path.exists():
                arch_type = "web"
                layers.append("api")
                evidence.append(Evidence(path=indicator))
                break

        for search_dir in [self.repo_path / "src", self.repo_path / "app", self.repo_path]:
            if not search_dir.exists():
                continue
            for item in search_dir.iterdir():
                if item.is_dir() and item.name in web_indicators:
                    arch_type = "web"
                    layers.append("api")
                    evidence.append(Evidence(path=str(item.relative_to(self.repo_path))))
                    break

        app_path = self.repo_path / "app"
        if app_path.exists() and app_path.is_dir():
            if arch_type == "unknown":
                arch_type = "web"
            layers.append("domain")

        desktop_extensions = [".ui", ".qml", ".xib", ".xaml"]
        for root, _, files in os.walk(self.repo_path):
            if ".git" in root:
                continue
            for file in files:
                if any(file.endswith(ext) for ext in desktop_extensions):
                    arch_type = "desktop"
                    evidence.append(Evidence(path=file))
                    break
            if arch_type == "desktop":
                break

        if arch_type == "unknown":
            cli_indicators = ["cli.py", "main.py", "cmd", "__main__.py"]
            for indicator in cli_indicators:
                if (self.repo_path / indicator).exists():
                    arch_type = "cli"
                    evidence.append(Evidence(path=indicator))
                    break

        if arch_type == "unknown":
            src_main = self.repo_path / "src" / "__main__.py"
            if src_main.exists():
                arch_type = "cli"
                evidence.append(Evidence(path="src/__main__.py"))

        if (self.repo_path / "Dockerfile").exists():
            layers.append("infra")
            evidence.append(Evidence(path="Dockerfile"))

        if (self.repo_path / "docker-compose.yml").exists():
            evidence.append(Evidence(path="docker-compose.yml"))

        if (self.repo_path / "docker-compose.yaml").exists():
            evidence.append(Evidence(path="docker-compose.yaml"))

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

        skip_dirs = {"node_modules", "vendor", ".git", "__pycache__", "venv", ".venv",
                     "env", "dist", "build", "eggs", ".eggs", ".tox", "htmlcov"}

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue

            for item in search_dir.iterdir():
                if not item.is_dir():
                    continue
                if item.name.startswith((".", "_")):
                    continue
                if item.name in skip_dirs:
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

    def _find_build_files(self) -> list[str]:
        if not self.repo_path:
            return []

        build_files = []
        candidates = [
            "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
            "Makefile", "setup.py", "pyproject.toml", "setup.cfg",
            "tox.ini", "noxfile.py", "justfile"
        ]

        for candidate in candidates:
            if (self.repo_path / candidate).exists():
                build_files.append(candidate)

        return build_files

    def _find_entrypoints(self) -> list[str]:
        if not self.repo_path:
            return []

        entrypoints = []
        candidates = [
            "main.py", "app.py", "manage.py", "wsgi.py", "asgi.py",
            "index.js", "app.js", "server.js", "main.go", "main.rs"
        ]

        for candidate in candidates:
            if (self.repo_path / candidate).exists():
                entrypoints.append(candidate)

        nested_candidates = [
            ("app", "main.py"),
            ("src", "main.py"),
            ("src", "__main__.py"),
        ]

        for parent, child in nested_candidates:
            path = self.repo_path / parent / child
            if path.exists():
                entrypoints.append(f"{parent}/{child}")

        return entrypoints

    def generate_facts_json(self) -> dict[str, Any]:
        languages = self.detect_languages()
        frameworks = self.detect_frameworks()
        architecture = self.detect_architecture_type()
        modules = self.extract_modules()

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
            "features": [],
            "runtime": {
                "dependencies": [],
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
