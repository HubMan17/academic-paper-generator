from dataclasses import dataclass, field


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
