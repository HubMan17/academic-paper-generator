import os
import re
from pathlib import Path

from .constants import SKIP_DIRS, DEEP_ROLE_MAPPING
from .models import APIEndpoint, ORMModel, FrontendRoute, Module, Feature, Evidence, DjangoModel, DRFEndpoint, PipelineStep
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


def extract_django_models(repo_path: Path) -> list[DjangoModel]:
    if not repo_path:
        return []

    models = []
    skip_classes = {"Model", "AbstractUser", "AbstractBaseUser", "PermissionsMixin"}

    model_class_pattern = re.compile(
        r'class\s+(\w+)\s*\((?:[^)]*(?:models\.Model|AbstractUser|AbstractBaseUser)[^)]*)\)\s*:'
    )
    field_pattern = re.compile(
        r'^\s+(\w+)\s*=\s*models\.(\w+)\s*\(([^)]*)\)',
        re.MULTILINE
    )
    fk_pattern = re.compile(
        r'models\.(?:ForeignKey|OneToOneField)\s*\(\s*["\']?(\w+)["\']?'
    )
    m2m_pattern = re.compile(
        r'models\.ManyToManyField\s*\(\s*["\']?(\w+)["\']?'
    )
    choices_pattern = re.compile(
        r'class\s+(\w+)\s*\([^)]*(?:TextChoices|IntegerChoices|Choices)[^)]*\)'
    )

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for file in files:
            if file != "models.py":
                continue

            file_path = Path(root) / file
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            if "models.Model" not in content and "AbstractUser" not in content:
                continue

            rel_path_str = rel_path(file_path, repo_path)
            app_name = Path(root).name

            class_matches = list(model_class_pattern.finditer(content))
            for i, match in enumerate(class_matches):
                class_name = match.group(1)

                if class_name in skip_classes:
                    continue

                start = match.end()
                end = class_matches[i + 1].start() if i + 1 < len(class_matches) else len(content)
                class_body = content[start:end]

                fields = []
                relationships = []

                for field_match in field_pattern.finditer(class_body):
                    field_name = field_match.group(1)
                    field_type = field_match.group(2)
                    field_args = field_match.group(3)

                    if field_name.startswith('_'):
                        continue

                    field_info = {"name": field_name, "type": field_type}

                    fk_match = fk_pattern.search(field_args) if "ForeignKey" in field_type or "OneToOne" in field_type else None
                    if fk_match:
                        target = fk_match.group(1)
                        relationships.append({"name": field_name, "target": target, "type": field_type})
                        field_info["foreign_key"] = target

                    m2m_match = m2m_pattern.search(field_args) if "ManyToMany" in field_type else None
                    if m2m_match:
                        target = m2m_match.group(1)
                        relationships.append({"name": field_name, "target": target, "type": "ManyToManyField"})

                    fields.append(field_info)

                choices = []
                for choice_match in choices_pattern.finditer(class_body):
                    choices.append(choice_match.group(1))

                meta = {}
                if choices:
                    meta["choices"] = choices

                models.append(DjangoModel(
                    name=class_name,
                    app=app_name,
                    fields=fields,
                    file=rel_path_str,
                    meta=meta,
                    relationships=relationships
                ))

    return models


def extract_drf_endpoints(repo_path: Path) -> list[DRFEndpoint]:
    if not repo_path:
        return []

    endpoints = []

    viewset_pattern = re.compile(
        r'class\s+(\w+)\s*\([^)]*(?:ViewSet|ModelViewSet|GenericViewSet|APIView)[^)]*\)'
    )
    serializer_pattern = re.compile(
        r'serializer_class\s*=\s*(\w+)'
    )
    permission_pattern = re.compile(
        r'permission_classes\s*=\s*\[([^\]]+)\]'
    )
    action_pattern = re.compile(
        r'@action\s*\([^)]*detail\s*=\s*(True|False)[^)]*(?:methods\s*=\s*\[([^\]]+)\])?[^)]*(?:url_path\s*=\s*["\']([^"\']+)["\'])?[^)]*\)\s*\n\s*def\s+(\w+)'
    )

    router_pattern = re.compile(
        r'router\.register\s*\(\s*[r]?["\']([^"\']+)["\']?\s*,\s*(\w+)'
    )
    path_pattern = re.compile(
        r'path\s*\(\s*["\']([^"\']+)["\']?\s*,\s*(\w+)\.as_view\(\)'
    )
    api_view_pattern = re.compile(
        r'@api_view\s*\(\s*\[([^\]]+)\]\s*\)\s*\ndef\s+(\w+)',
        re.MULTILINE
    )
    extend_schema_tags_pattern = re.compile(
        r'@extend_schema\s*\([^)]*tags\s*=\s*\["([^"]+)"\]'
    )
    path_to_view_pattern = re.compile(
        r'path\s*\(\s*["\']([^"\']+)["\']?\s*,\s*(\w+)\s*,'
    )

    view_to_path = {}
    viewset_to_prefix = {}

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for file in files:
            if file != "urls.py":
                continue

            file_path = Path(root) / file
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            for match in router_pattern.finditer(content):
                prefix = match.group(1)
                viewset_name = match.group(2)
                viewset_to_prefix[viewset_name] = prefix

            for match in path_pattern.finditer(content):
                path = match.group(1)
                view_name = match.group(2)
                viewset_to_prefix[view_name] = path

            for match in path_to_view_pattern.finditer(content):
                url_path = match.group(1)
                view_name = match.group(2)
                view_to_path[view_name] = url_path

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for file in files:
            if file not in ["views.py", "viewsets.py"] and not file.endswith("_views.py"):
                continue

            file_path = Path(root) / file
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            rel_path_str = rel_path(file_path, repo_path)

            for match in api_view_pattern.finditer(content):
                methods_str = match.group(1)
                func_name = match.group(2)
                methods = [m.strip().strip('"\'').upper() for m in methods_str.split(',')]

                url_path = view_to_path.get(func_name, func_name.replace('_', '/'))

                tag = ""
                search_start = max(0, match.start() - 500)
                search_area = content[search_start:match.start()]
                tag_match = extend_schema_tags_pattern.search(search_area)
                if tag_match:
                    tag = tag_match.group(1)

                for method in methods:
                    endpoints.append(DRFEndpoint(
                        method=method,
                        path=f"/api/v1/{url_path}",
                        viewset=tag or "api",
                        action=func_name,
                        file=rel_path_str,
                        serializer="",
                        permission_classes=[]
                    ))

            if "ViewSet" not in content and "APIView" not in content:
                continue

            class_matches = list(viewset_pattern.finditer(content))
            for i, match in enumerate(class_matches):
                viewset_name = match.group(1)

                start = match.end()
                end = class_matches[i + 1].start() if i + 1 < len(class_matches) else len(content)
                class_body = content[start:end]

                serializer = ""
                serializer_match = serializer_pattern.search(class_body)
                if serializer_match:
                    serializer = serializer_match.group(1)

                permissions = []
                perm_match = permission_pattern.search(class_body)
                if perm_match:
                    perms = perm_match.group(1)
                    permissions = [p.strip() for p in perms.split(',') if p.strip()]

                prefix = viewset_to_prefix.get(viewset_name, viewset_name.lower().replace("viewset", ""))

                if "ModelViewSet" in content[match.start():match.end()+100]:
                    for method, action in [("GET", "list"), ("POST", "create"), ("GET", "retrieve"), ("PUT", "update"), ("PATCH", "partial_update"), ("DELETE", "destroy")]:
                        path = f"/api/v1/{prefix}/" if action in ["list", "create"] else f"/api/v1/{prefix}/{{id}}/"
                        endpoints.append(DRFEndpoint(
                            method=method,
                            path=path,
                            viewset=viewset_name,
                            action=action,
                            file=rel_path_str,
                            serializer=serializer,
                            permission_classes=permissions
                        ))

                for action_match in action_pattern.finditer(class_body):
                    detail = action_match.group(1) == "True"
                    methods_str = action_match.group(2) or '"get"'
                    url_path = action_match.group(3) or action_match.group(4)
                    action_name = action_match.group(4)

                    methods = [m.strip().strip('"\'').upper() for m in methods_str.split(',')]

                    for method in methods:
                        if detail:
                            path = f"/api/v1/{prefix}/{{id}}/{url_path}/"
                        else:
                            path = f"/api/v1/{prefix}/{url_path}/"

                        endpoints.append(DRFEndpoint(
                            method=method,
                            path=path,
                            viewset=viewset_name,
                            action=action_name,
                            file=rel_path_str,
                            serializer=serializer,
                            permission_classes=permissions
                        ))

    return endpoints


def extract_pipeline_steps(repo_path: Path) -> list[PipelineStep]:
    if not repo_path:
        return []

    steps = []

    ensure_pattern = re.compile(
        r'def\s+(ensure_\w+)\s*\(\s*\n?\s*document_id'
    )
    kind_pattern = re.compile(
        r'kind\s*=\s*(?:ArtifactKind\.)?(\w+)(?:\.value)?'
    )
    docstring_pattern = re.compile(
        r'"""([^"]+)"""'
    )

    steps_dir = repo_path / "server" / "services" / "pipeline" / "steps"
    if not steps_dir.exists():
        pipeline_dir = repo_path / "services" / "pipeline" / "steps"
        if pipeline_dir.exists():
            steps_dir = pipeline_dir
        else:
            return []

    for file_path in steps_dir.glob("*.py"):
        if file_path.name.startswith("_"):
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        rel_path_str = rel_path(file_path, repo_path)

        for match in ensure_pattern.finditer(content):
            func_name = match.group(1)
            start = match.start()

            kind = ""
            kind_search_area = content[start:start+500]
            kind_match = kind_pattern.search(kind_search_area)
            if kind_match:
                kind = kind_match.group(1)

            description = ""
            doc_match = docstring_pattern.search(kind_search_area)
            if doc_match:
                description = doc_match.group(1).strip()[:100]

            steps.append(PipelineStep(
                name=func_name,
                kind=kind,
                file=rel_path_str,
                description=description
            ))

    return steps


def extract_artifact_kinds(repo_path: Path) -> list[dict]:
    kinds = []

    kinds_file = repo_path / "server" / "services" / "pipeline" / "kinds.py"
    if not kinds_file.exists():
        kinds_file = repo_path / "services" / "pipeline" / "kinds.py"
        if not kinds_file.exists():
            return []

    try:
        content = kinds_file.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    kind_pattern = re.compile(r'(\w+)\s*=\s*["\']([^"\']+)["\']')

    for match in kind_pattern.finditer(content):
        name = match.group(1)
        value = match.group(2)
        if name.isupper():
            kinds.append({"name": name, "value": value})

    return kinds
