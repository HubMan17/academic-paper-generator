import os
from pathlib import Path

from .constants import SKIP_DIRS


def normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def rel_path(path: Path, repo_path: Path) -> str:
    return normalize_path(str(path.relative_to(repo_path)))


def find_files_recursive(repo_path: Path, filename: str) -> list[Path]:
    if not repo_path:
        return []

    found = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if filename in files:
            found.append(Path(root) / filename)
    return found


def find_dirs_recursive(repo_path: Path, dirname: str) -> list[Path]:
    if not repo_path:
        return []

    found = []
    for root, dirs, _ in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if dirname in dirs:
            found.append(Path(root) / dirname)
    return found


def count_lines(file_path: Path) -> int:
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = [l for l in content.splitlines() if l.strip() and not l.strip().startswith(("#", "//", "/*", "*"))]
        return len(lines)
    except Exception:
        return 0
