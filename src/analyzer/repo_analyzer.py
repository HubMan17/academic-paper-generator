"""
Repository Analyzer

Модуль для клонирования и анализа Git-репозиториев.
Извлекает факты о проекте и формирует facts.json.
"""

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
    """Доказательство факта - ссылка на файл/строки."""
    path: str
    lines: list[int] = field(default_factory=list)


@dataclass
class Language:
    """Информация о языке программирования."""
    name: str
    ratio: float
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class Framework:
    """Информация о фреймворке/библиотеке."""
    name: str
    type: str  # web, desktop, cli, library
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class Module:
    """Информация о модуле проекта."""
    name: str
    role: str
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class Feature:
    """Информация о функциональности."""
    id: str
    summary: str
    evidence: list[Evidence] = field(default_factory=list)


class RepoAnalyzer:
    """
    Анализатор Git-репозиториев.

    Выполняет:
    - Клонирование репозитория
    - Очистку по .gitignore и правилам "шаблонного мусора"
    - Определение языков, фреймворков, архитектуры
    - Извлечение модулей и features
    - Генерацию facts.json
    """

    FACTS_SCHEMA = "facts.v1"

    # Паттерны для определения "шаблонного мусора"
    TEMPLATE_PATTERNS = [
        "README-template*",
        "TEMPLATE*",
        ".github/ISSUE_TEMPLATE*",
        ".github/PULL_REQUEST_TEMPLATE*",
    ]

    # Файлы зависимостей для разных языков
    DEPENDENCY_FILES = {
        "python": ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"],
        "javascript": ["package.json", "package-lock.json", "yarn.lock"],
        "go": ["go.mod", "go.sum"],
        "java": ["pom.xml", "build.gradle"],
        "rust": ["Cargo.toml"],
    }

    def __init__(self, repo_url: str, work_dir: str | None = None):
        """
        Инициализация анализатора.

        Args:
            repo_url: URL публичного Git-репозитория
            work_dir: Рабочая директория (по умолчанию - временная)
        """
        self.repo_url = repo_url
        self.work_dir = work_dir or tempfile.mkdtemp()
        self.repo_path: Path | None = None
        self.commit_sha: str | None = None

    def clone_repository(self) -> Path:
        """
        Клонирует репозиторий.

        Returns:
            Путь к склонированному репозиторию

        Raises:
            RuntimeError: Если клонирование не удалось
        """
        # Проверка доступности репозитория
        result = subprocess.run(
            ["git", "ls-remote", self.repo_url],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"Repository not accessible: {result.stderr}")

        # Клонирование с depth=1
        repo_name = self.repo_url.rstrip("/").split("/")[-1].replace(".git", "")
        self.repo_path = Path(self.work_dir) / repo_name

        result = subprocess.run(
            ["git", "clone", "--depth=1", self.repo_url, str(self.repo_path)],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"Clone failed: {result.stderr}")

        # Получение SHA коммита
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True
        )
        self.commit_sha = result.stdout.strip()

        return self.repo_path

    def detect_languages(self) -> list[Language]:
        """
        Определяет языки программирования в репозитории.

        Использует расширения файлов для подсчёта.
        TODO: Интеграция с enry для более точного определения.

        Returns:
            Список языков с процентным соотношением
        """
        if not self.repo_path:
            raise RuntimeError("Repository not cloned")

        # Подсчёт файлов по расширениям
        extension_counts: dict[str, int] = {}
        extension_to_lang = {
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

        for root, _, files in os.walk(self.repo_path):
            # Пропускаем .git и vendor директории
            if ".git" in root or "vendor" in root or "node_modules" in root:
                continue
            for file in files:
                ext = Path(file).suffix.lower()
                if ext in extension_to_lang:
                    lang = extension_to_lang[ext]
                    extension_counts[lang] = extension_counts.get(lang, 0) + 1

        total = sum(extension_counts.values())
        if total == 0:
            return []

        languages = []
        for lang, count in sorted(extension_counts.items(), key=lambda x: -x[1]):
            ratio = round(count / total, 2)
            languages.append(Language(
                name=lang,
                ratio=ratio,
                evidence=[Evidence(path=f"*.{ext}" for ext, l in extension_to_lang.items() if l == lang)]
            ))

        return languages

    def detect_frameworks(self) -> list[Framework]:
        """
        Определяет фреймворки и библиотеки.

        Анализирует файлы зависимостей (package.json, requirements.txt и т.д.)

        Returns:
            Список обнаруженных фреймворков
        """
        if not self.repo_path:
            raise RuntimeError("Repository not cloned")

        frameworks = []

        # Проверка Python зависимостей
        requirements_path = self.repo_path / "requirements.txt"
        if requirements_path.exists():
            content = requirements_path.read_text()
            python_frameworks = {
                "django": ("Django", "web"),
                "fastapi": ("FastAPI", "web"),
                "flask": ("Flask", "web"),
                "celery": ("Celery", "task-queue"),
                "pytest": ("pytest", "testing"),
            }
            for key, (name, fw_type) in python_frameworks.items():
                if key in content.lower():
                    frameworks.append(Framework(
                        name=name,
                        type=fw_type,
                        evidence=[Evidence(path="requirements.txt")]
                    ))

        # Проверка pyproject.toml
        pyproject_path = self.repo_path / "pyproject.toml"
        if pyproject_path.exists():
            content = pyproject_path.read_text()
            # TODO: Полноценный парсинг TOML
            if "django" in content.lower():
                frameworks.append(Framework(
                    name="Django",
                    type="web",
                    evidence=[Evidence(path="pyproject.toml")]
                ))

        # Проверка package.json для JS/TS проектов
        package_json_path = self.repo_path / "package.json"
        if package_json_path.exists():
            try:
                with open(package_json_path) as f:
                    package_data = json.load(f)
                deps = {
                    **package_data.get("dependencies", {}),
                    **package_data.get("devDependencies", {})
                }
                js_frameworks = {
                    "react": ("React", "frontend"),
                    "vue": ("Vue.js", "frontend"),
                    "next": ("Next.js", "fullstack"),
                    "express": ("Express", "backend"),
                    "nestjs": ("NestJS", "backend"),
                }
                for key, (name, fw_type) in js_frameworks.items():
                    if any(key in dep.lower() for dep in deps.keys()):
                        frameworks.append(Framework(
                            name=name,
                            type=fw_type,
                            evidence=[Evidence(path="package.json")]
                        ))
            except json.JSONDecodeError:
                pass

        return frameworks

    def detect_architecture_type(self) -> dict[str, Any]:
        """
        Определяет архитектурный тип проекта.

        Правила:
        - Наличие routes/controllers + веб-зависимости -> web/api
        - GUI-ресурсы (.ui, .qml, .xib) -> desktop
        - Только cli/main без веб-зависимостей -> cli

        Returns:
            Словарь с типом архитектуры и слоями
        """
        if not self.repo_path:
            raise RuntimeError("Repository not cloned")

        arch_type = "unknown"
        layers = []
        evidence = []

        # Проверка на web/api
        web_indicators = ["routes", "controllers", "views", "api", "endpoints"]
        for indicator in web_indicators:
            indicator_path = self.repo_path / indicator
            if indicator_path.exists():
                arch_type = "web"
                layers.append("api")
                evidence.append(Evidence(path=indicator))
                break

        # Проверка на наличие app директории
        app_path = self.repo_path / "app"
        if app_path.exists() and app_path.is_dir():
            if arch_type == "unknown":
                arch_type = "web"
            layers.append("domain")

        # Проверка на desktop приложение
        desktop_extensions = [".ui", ".qml", ".xib", ".xaml"]
        for root, _, files in os.walk(self.repo_path):
            for file in files:
                if any(file.endswith(ext) for ext in desktop_extensions):
                    arch_type = "desktop"
                    evidence.append(Evidence(path=file))
                    break

        # Проверка на CLI
        if arch_type == "unknown":
            cli_indicators = ["cli.py", "main.py", "cmd", "__main__.py"]
            for indicator in cli_indicators:
                if (self.repo_path / indicator).exists():
                    arch_type = "cli"
                    evidence.append(Evidence(path=indicator))
                    break

        # Проверка Docker
        if (self.repo_path / "Dockerfile").exists():
            layers.append("infra")
            evidence.append(Evidence(path="Dockerfile"))

        if (self.repo_path / "docker-compose.yml").exists():
            evidence.append(Evidence(path="docker-compose.yml"))

        return {
            "type": arch_type,
            "layers": list(set(layers)) or ["unknown"],
            "evidence": [{"path": e.path, "lines": e.lines} for e in evidence]
        }

    def extract_modules(self) -> list[Module]:
        """
        Извлекает модули проекта.

        Анализирует директории верхнего уровня и именование
        (users, auth, billing, core, infra, domain).

        Returns:
            Список модулей с их ролями
        """
        if not self.repo_path:
            raise RuntimeError("Repository not cloned")

        modules = []

        # Известные роли модулей
        role_mapping = {
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

        # Поиск в src/, app/ или корне
        search_dirs = [
            self.repo_path / "src",
            self.repo_path / "app",
            self.repo_path,
        ]

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue

            for item in search_dir.iterdir():
                if item.is_dir() and not item.name.startswith((".", "_")):
                    if item.name in ["node_modules", "vendor", ".git", "__pycache__"]:
                        continue

                    role = role_mapping.get(item.name.lower(), "module")
                    modules.append(Module(
                        name=item.name,
                        role=role,
                        evidence=[Evidence(path=str(item.relative_to(self.repo_path)))]
                    ))

        return modules

    def generate_facts_json(self) -> dict[str, Any]:
        """
        Генерирует facts.json со всеми извлечёнными фактами.

        Returns:
            Словарь в формате facts.json v1
        """
        languages = self.detect_languages()
        frameworks = self.detect_frameworks()
        architecture = self.detect_architecture_type()
        modules = self.extract_modules()

        facts = {
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
            "features": [],  # TODO: Извлечение features из роутинга
            "runtime": {
                "dependencies": [],  # TODO: Парсинг зависимостей
                "build_files": self._find_build_files(),
                "entrypoints": self._find_entrypoints()
            }
        }

        return facts

    def _find_build_files(self) -> list[str]:
        """Находит файлы сборки (Dockerfile, docker-compose и т.д.)"""
        if not self.repo_path:
            return []

        build_files = []
        candidates = ["Dockerfile", "docker-compose.yml", "docker-compose.yaml",
                      "Makefile", "setup.py", "pyproject.toml"]

        for candidate in candidates:
            if (self.repo_path / candidate).exists():
                build_files.append(candidate)

        return build_files

    def _find_entrypoints(self) -> list[str]:
        """Находит точки входа приложения."""
        if not self.repo_path:
            return []

        entrypoints = []
        candidates = ["main.py", "app.py", "manage.py", "wsgi.py",
                      "index.js", "app.js", "server.js", "main.go"]

        for candidate in candidates:
            if (self.repo_path / candidate).exists():
                entrypoints.append(candidate)

        # Проверка app/main.py
        app_main = self.repo_path / "app" / "main.py"
        if app_main.exists():
            entrypoints.append("app/main.py")

        return entrypoints

    def analyze(self) -> dict[str, Any]:
        """
        Выполняет полный анализ репозитория.

        Returns:
            facts.json
        """
        self.clone_repository()
        return self.generate_facts_json()

    def save_facts(self, output_path: str | Path) -> None:
        """
        Сохраняет facts.json в файл.

        Args:
            output_path: Путь для сохранения
        """
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
