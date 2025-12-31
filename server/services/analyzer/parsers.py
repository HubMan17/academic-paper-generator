import json
import re
from pathlib import Path

from .models import Dependency, Evidence


def parse_requirements_txt(path: Path, rel_path_str: str) -> list[Dependency]:
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
                deps.append(Dependency(
                    name=name,
                    version=version.strip(),
                    evidence=[Evidence(path=rel_path_str)]
                ))
    except Exception:
        pass
    return deps


def parse_package_json(path: Path, rel_path_str: str) -> tuple[list[Dependency], dict]:
    deps = []
    package_data = {}
    try:
        content = path.read_text(encoding="utf-8")
        package_data = json.loads(content)

        for dep_type in ["dependencies", "devDependencies"]:
            for name, version in package_data.get(dep_type, {}).items():
                deps.append(Dependency(
                    name=name.lower(),
                    version=version,
                    evidence=[Evidence(path=rel_path_str)]
                ))
    except Exception:
        pass
    return deps, package_data


def extract_column_type(type_str: str) -> str:
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
