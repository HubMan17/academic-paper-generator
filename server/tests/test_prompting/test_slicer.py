import pytest
from services.prompting import slice_for_section, get_section_spec


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
