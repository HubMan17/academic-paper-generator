import json
import tempfile
from pathlib import Path
from typing import Any

from .git import clone_repository
from .facts import generate_facts_json


class RepoAnalyzer:
    def __init__(self, repo_url: str, work_dir: str | None = None):
        self.repo_url = repo_url
        self.work_dir = work_dir or tempfile.mkdtemp()
        self.repo_path: Path | None = None
        self.commit_sha: str | None = None

    def clone(self) -> Path:
        self.repo_path, self.commit_sha = clone_repository(self.repo_url, self.work_dir)
        return self.repo_path

    def generate_facts(self) -> dict[str, Any]:
        if not self.repo_path or not self.commit_sha:
            raise RuntimeError("Repository not cloned. Call clone() first.")
        return generate_facts_json(self.repo_path, self.repo_url, self.commit_sha)

    def analyze(self) -> dict[str, Any]:
        self.clone()
        return self.generate_facts()

    def save_facts(self, output_path: str | Path) -> None:
        facts = self.generate_facts()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(facts, f, ensure_ascii=False, indent=2)
