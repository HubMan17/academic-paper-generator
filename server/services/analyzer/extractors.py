import os
import re
from pathlib import Path

from .constants import SKIP_DIRS, DEEP_ROLE_MAPPING
from .models import APIEndpoint, ORMModel, FrontendRoute, Module, Feature, Evidence
from .parsers import extract_column_type
from .utils import rel_path


def extract_fastapi_routes(repo_path: Path) -> list[APIEndpoint]:
    if not repo_path:
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

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for file in files:
            if not file.endswith(".py"):
                continue

            file_path = Path(root) / file
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            rel_path_str = rel_path(file_path, repo_path)

            for match in router_prefix_pattern.finditer(content):
                prefix = match.group(1)
                file_prefixes[rel_path_str] = prefix

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for file in files:
            if file != "main.py" and file != "app.py":
                continue

            file_path = Path(root) / file
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            rel_path_str = rel_path(file_path, repo_path)

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
                    f"{rel_path(parent_path, repo_path)}/routers/{module_name}.py",
                    f"{rel_path(parent_path, repo_path)}/{module_name}.py",
                    f"{rel_path(parent_path, repo_path)}/routes/{module_name}.py",
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

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for file in files:
            if not file.endswith(".py"):
                continue

            file_path = Path(root) / file
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            rel_path_str = rel_path(file_path, repo_path)

            current_router = "app"
            router_match = re.search(r'(\w+)\s*=\s*APIRouter', content)
            if router_match:
                current_router = router_match.group(1)

            router_tags = []
            tags_match = router_tags_pattern.search(content)
            if tags_match:
                raw_tags = tags_match.group(1)
                router_tags = [t.strip().strip('"\'') for t in raw_tags.split(',')]

            prefix = file_prefixes.get(rel_path_str, "")

            if not prefix and ("routers/" in rel_path_str or "routes/" in rel_path_str):
                dir_name = Path(rel_path_str).stem
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
                    file=rel_path_str,
                    tags=tags,
                    auth_required=auth_required,
                    description=description
                ))

    return endpoints


def extract_orm_models(repo_path: Path) -> list[ORMModel]:
    if not repo_path:
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

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

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

            rel_path_str = rel_path(file_path, repo_path)

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
                    field_type = extract_column_type(raw_type)

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
                    file=rel_path_str
                )
                if relationships:
                    model.relationships = relationships

                models.append(model)

    return models


def extract_frontend_routes(repo_path: Path) -> list[FrontendRoute]:
    if not repo_path:
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

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

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

            rel_path_str = rel_path(file_path, repo_path)

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
                    file=rel_path_str,
                    auth_required=auth_required
                ))

            for match in react_route_pattern.finditer(content):
                path = match.group(1)
                component = match.group(2) or match.group(3) or ""

                routes.append(FrontendRoute(
                    path=path,
                    name="",
                    component=component,
                    file=rel_path_str,
                    auth_required=False
                ))

    return routes


def extract_deep_modules(repo_path: Path) -> list[Module]:
    if not repo_path:
        raise RuntimeError("Repository not cloned")

    modules = []
    processed = set()

    top_level_dirs = ["backend", "frontend", "server", "client", "api", "web", "src", "app"]

    for tld in top_level_dirs:
        tld_path = repo_path / tld
        if not tld_path.exists() or not tld_path.is_dir():
            continue

        for item in tld_path.iterdir():
            if not item.is_dir():
                continue
            if item.name.startswith((".", "_")) or item.name in SKIP_DIRS:
                continue

            module_path = f"{tld}/{item.name}"
            if module_path in processed:
                continue
            processed.add(module_path)

            role = DEEP_ROLE_MAPPING.get(item.name.lower(), "module")

            submodules = []
            for sub in item.iterdir():
                if sub.is_dir() and not sub.name.startswith((".", "_")) and sub.name not in SKIP_DIRS:
                    sub_role = DEEP_ROLE_MAPPING.get(sub.name.lower(), "submodule")
                    submodules.append(f"{sub.name}:{sub_role}")

            modules.append(Module(
                name=item.name,
                role=role,
                path=module_path,
                submodules=submodules,
                evidence=[Evidence(path=module_path)]
            ))

    for item in repo_path.iterdir():
        if not item.is_dir():
            continue
        if item.name.startswith((".", "_")) or item.name in SKIP_DIRS:
            continue
        if item.name.lower() in [t.lower() for t in top_level_dirs]:
            continue

        module_path = item.name
        if module_path in processed:
            continue
        processed.add(module_path)

        role = DEEP_ROLE_MAPPING.get(item.name.lower(), "top-level")

        modules.append(Module(
            name=item.name,
            role=role,
            path=module_path,
            submodules=[],
            evidence=[Evidence(path=module_path)]
        ))

    return modules


def extract_features(repo_path: Path, endpoints: list[APIEndpoint]) -> list[Feature]:
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
