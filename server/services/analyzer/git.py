import subprocess
import tempfile
from pathlib import Path


def check_repo_accessible(repo_url: str) -> bool:
    result = subprocess.run(
        ["git", "ls-remote", repo_url],
        capture_output=True,
        text=True
    )
    return result.returncode == 0


def clone_repository(repo_url: str, work_dir: str | None = None) -> tuple[Path, str]:
    if not check_repo_accessible(repo_url):
        raise RuntimeError(f"Repository not accessible: {repo_url}")

    work_dir = work_dir or tempfile.mkdtemp()
    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    repo_path = Path(work_dir) / repo_name

    result = subprocess.run(
        ["git", "clone", "--depth=1", repo_url, str(repo_path)],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"Clone failed: {result.stderr}")

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True
    )
    commit_sha = result.stdout.strip()

    return repo_path, commit_sha
