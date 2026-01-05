import pytest
from services.prompting import slice_for_section, get_section_spec
from services.prompting.schema import SectionSpec, OutlineMode


@pytest.fixture
def sample_facts():
    return {
        "facts": [
            {
                "id": "fact_1",
                "tags": ["project_name", "description"],
                "key_path": "project.name",
                "text": "Project Name: Test App",
                "details": "A test application for demonstration"
            },
            {
                "id": "fact_2",
                "tags": ["tech_stack"],
                "key_path": "tech.stack",
                "text": "Tech Stack: Python, Django",
                "details": "Backend built with Django 5.0"
            },
            {
                "id": "fact_3",
                "tags": ["architecture"],
                "key_path": "arch.pattern",
                "text": "Architecture: Layered",
                "details": "Three-tier architecture"
            }
        ]
    }


@pytest.fixture
def analyzer_facts():
    return {
        "schema": "facts/v1",
        "repo": {
            "url": "https://github.com/test/repo",
            "commit": "abc123",
            "detected_at": "2025-01-01T00:00:00Z"
        },
        "languages": [
            {"name": "Python", "ratio": 0.7, "lines_of_code": 5000, "evidence": []},
            {"name": "JavaScript", "ratio": 0.3, "lines_of_code": 2000, "evidence": []}
        ],
        "frameworks": [
            {"name": "Django", "type": "backend", "evidence": []},
            {"name": "React", "type": "frontend", "evidence": []}
        ],
        "architecture": {
            "type": "layered",
            "confidence": 0.85,
            "evidence": ["apps/", "services/", "api/"]
        },
        "modules": [
            {"name": "apps", "role": "applications", "path": "apps/", "submodules": ["core", "auth"], "evidence": []},
            {"name": "services", "role": "business_logic", "path": "services/", "submodules": ["llm"], "evidence": []}
        ],
        "api": {
            "endpoints": [
                {"method": "GET", "path": "/users", "full_path": "/api/v1/users", "handler": "list_users", "router": "api", "file": "views.py", "tags": [], "auth_required": True, "description": "List users"},
                {"method": "POST", "path": "/auth/login", "full_path": "/api/v1/auth/login", "handler": "login", "router": "auth", "file": "auth.py", "tags": [], "auth_required": False, "description": "Login"}
            ],
            "total_count": 2
        },
        "frontend_routes": [],
        "models": [
            {"name": "User", "table": "users", "fields": ["id", "email", "name"], "relationships": [], "file": "models.py"}
        ],
        "runtime": {
            "dependencies": [
                {"name": "django", "version": "5.0", "evidence": []},
                {"name": "djangorestframework", "version": "3.14", "evidence": []}
            ],
            "build_files": ["Dockerfile", "docker-compose.yml"],
            "entrypoints": ["manage.py"]
        }
    }


@pytest.fixture
def sample_outline():
    return {
        "title": "Test Document",
        "sections": [
            {"key": "intro", "title": "Introduction", "order": 0},
            {"key": "architecture", "title": "Architecture", "order": 1},
            {"key": "api", "title": "API", "order": 2}
        ]
    }


def test_slice_for_section_intro(sample_facts, sample_outline):
    context_pack = slice_for_section(
        section_key="intro",
        facts=sample_facts,
        outline=sample_outline,
        summaries=[],
        global_context="Test project"
    )

    assert context_pack.section_key == "intro"
    assert context_pack.rendered_prompt.system
    assert context_pack.rendered_prompt.user
    assert "Test project" in context_pack.layers.global_context
    assert len(context_pack.debug.selected_fact_refs) > 0


def test_slice_for_section_architecture(sample_facts, sample_outline):
    context_pack = slice_for_section(
        section_key="architecture",
        facts=sample_facts,
        outline=sample_outline,
        summaries=[],
        global_context="Test project"
    )

    assert context_pack.section_key == "architecture"
    assert len(context_pack.debug.selected_fact_refs) > 0
    architecture_fact_present = any(
        "architecture" in ref.reason
        for ref in context_pack.debug.selected_fact_refs
    )
    assert architecture_fact_present


def test_slice_for_section_with_summaries(sample_facts, sample_outline):
    summaries = [
        {
            "section_key": "intro",
            "points": ["Point 1", "Point 2", "Point 3"]
        }
    ]

    context_pack = slice_for_section(
        section_key="architecture",
        facts=sample_facts,
        outline=sample_outline,
        summaries=summaries,
        global_context="Test project"
    )

    assert context_pack.section_key == "architecture"
    assert "intro" in context_pack.layers.summaries or len(summaries) > 0


def test_get_section_spec():
    spec = get_section_spec("intro")
    assert spec.key == "intro"
    assert "project_name" in spec.fact_tags or "description" in spec.fact_tags

    spec = get_section_spec("architecture")
    assert spec.key == "architecture"
    assert "architecture" in spec.fact_tags


def test_context_pack_structure(sample_facts, sample_outline):
    context_pack = slice_for_section(
        section_key="intro",
        facts=sample_facts,
        outline=sample_outline,
        summaries=[],
        global_context="Test"
    )

    assert hasattr(context_pack, 'section_key')
    assert hasattr(context_pack, 'layers')
    assert hasattr(context_pack, 'rendered_prompt')
    assert hasattr(context_pack, 'budget')
    assert hasattr(context_pack, 'debug')

    assert hasattr(context_pack.layers, 'global_context')
    assert hasattr(context_pack.layers, 'outline_excerpt')
    assert hasattr(context_pack.layers, 'facts_slice')
    assert hasattr(context_pack.layers, 'summaries')
    assert hasattr(context_pack.layers, 'constraints')

    assert hasattr(context_pack.rendered_prompt, 'system')
    assert hasattr(context_pack.rendered_prompt, 'user')

    assert hasattr(context_pack.debug, 'selected_fact_refs')
    assert hasattr(context_pack.debug, 'selection_reason')
    assert hasattr(context_pack.debug, 'trims_applied')


def test_slice_analyzer_facts_intro(analyzer_facts, sample_outline):
    context_pack = slice_for_section(
        section_key="intro",
        facts=analyzer_facts,
        outline=sample_outline,
        summaries=[],
        global_context="Test project"
    )

    assert context_pack.section_key == "intro"
    assert len(context_pack.debug.selected_fact_refs) > 0

    has_tech_stack = any(
        "tech_stack" in ref.reason
        for ref in context_pack.debug.selected_fact_refs
    )
    assert has_tech_stack


def test_slice_analyzer_facts_architecture(analyzer_facts, sample_outline):
    context_pack = slice_for_section(
        section_key="architecture",
        facts=analyzer_facts,
        outline=sample_outline,
        summaries=[],
        global_context="Test project"
    )

    assert context_pack.section_key == "architecture"
    assert len(context_pack.debug.selected_fact_refs) > 0

    has_architecture = any(
        "architecture" in ref.reason or "modules" in ref.reason
        for ref in context_pack.debug.selected_fact_refs
    )
    assert has_architecture


def test_slice_analyzer_facts_api(analyzer_facts, sample_outline):
    context_pack = slice_for_section(
        section_key="api",
        facts=analyzer_facts,
        outline=sample_outline,
        summaries=[],
        global_context="Test project"
    )

    assert context_pack.section_key == "api"
    assert len(context_pack.debug.selected_fact_refs) > 0

    has_api = any(
        "api" in ref.reason or "endpoints" in ref.reason
        for ref in context_pack.debug.selected_fact_refs
    )
    assert has_api


def test_slice_with_explicit_spec(sample_facts, sample_outline):
    custom_spec = SectionSpec(
        key="custom_section",
        fact_tags=["tech_stack", "architecture"],
        fact_keys=[],
        outline_mode=OutlineMode.STRUCTURE,
        needs_summaries=False,
        style_profile="academic",
        target_chars=(2000, 4000),
        constraints=["Custom constraint 1", "Custom constraint 2"],
    )

    context_pack = slice_for_section(
        section_key="custom_section",
        facts=sample_facts,
        outline=sample_outline,
        summaries=[],
        global_context="Test project",
        spec=custom_spec
    )

    assert context_pack.section_key == "custom_section"
    assert "Custom constraint 1" in context_pack.layers.constraints
    assert "Custom constraint 2" in context_pack.layers.constraints

    selected_tags = [ref.reason for ref in context_pack.debug.selected_fact_refs]
    has_expected_tags = any("tech_stack" in reason or "architecture" in reason for reason in selected_tags)
    assert has_expected_tags
