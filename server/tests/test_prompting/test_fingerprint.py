import pytest
from services.prompting import (
    slice_for_section,
    compute_prompt_fingerprint,
    PROMPT_VERSION,
    Budget,
    RenderedPrompt
)


@pytest.fixture
def sample_facts():
    return {
        "facts": [
            {
                "id": "fact_1",
                "tags": ["project_name", "description"],
                "key_path": "project.name",
                "text": "Project Name: Test App",
                "details": "A test application"
            },
            {
                "id": "fact_2",
                "tags": ["tech_stack"],
                "key_path": "tech.stack",
                "text": "Tech Stack: Python, Django",
                "details": "Django 5.0"
            },
            {
                "id": "fact_3",
                "tags": ["architecture"],
                "key_path": "arch.pattern",
                "text": "Architecture: Layered",
                "details": "Three-tier"
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
        ]
    }


def test_fingerprint_is_computed(sample_facts, sample_outline):
    context_pack = slice_for_section(
        section_key="intro",
        facts=sample_facts,
        outline=sample_outline,
        summaries=[],
        global_context="Test project"
    )

    assert context_pack.prompt_fingerprint
    assert len(context_pack.prompt_fingerprint) == 16
    assert context_pack.prompt_version == PROMPT_VERSION


def test_fingerprint_stability_same_input(sample_facts, sample_outline):
    pack1 = slice_for_section(
        section_key="intro",
        facts=sample_facts,
        outline=sample_outline,
        summaries=[],
        global_context="Test project"
    )

    pack2 = slice_for_section(
        section_key="intro",
        facts=sample_facts,
        outline=sample_outline,
        summaries=[],
        global_context="Test project"
    )

    assert pack1.prompt_fingerprint == pack2.prompt_fingerprint
    assert pack1.prompt_version == pack2.prompt_version


def test_fingerprint_changes_with_different_facts(sample_outline):
    facts1 = {
        "facts": [
            {"id": "fact_1", "tags": ["project_name"], "key_path": "a", "text": "Fact 1"}
        ]
    }
    facts2 = {
        "facts": [
            {"id": "fact_2", "tags": ["project_name"], "key_path": "b", "text": "Fact 2"}
        ]
    }

    pack1 = slice_for_section(
        section_key="intro",
        facts=facts1,
        outline=sample_outline,
        summaries=[],
        global_context="Test"
    )

    pack2 = slice_for_section(
        section_key="intro",
        facts=facts2,
        outline=sample_outline,
        summaries=[],
        global_context="Test"
    )

    assert pack1.prompt_fingerprint != pack2.prompt_fingerprint


def test_fingerprint_changes_with_different_section(sample_facts, sample_outline):
    pack1 = slice_for_section(
        section_key="intro",
        facts=sample_facts,
        outline=sample_outline,
        summaries=[],
        global_context="Test"
    )

    pack2 = slice_for_section(
        section_key="architecture",
        facts=sample_facts,
        outline=sample_outline,
        summaries=[],
        global_context="Test"
    )

    assert pack1.prompt_fingerprint != pack2.prompt_fingerprint


def test_fingerprint_changes_with_different_context(sample_facts, sample_outline):
    pack1 = slice_for_section(
        section_key="intro",
        facts=sample_facts,
        outline=sample_outline,
        summaries=[],
        global_context="Project Alpha"
    )

    pack2 = slice_for_section(
        section_key="intro",
        facts=sample_facts,
        outline=sample_outline,
        summaries=[],
        global_context="Project Beta"
    )

    assert pack1.prompt_fingerprint != pack2.prompt_fingerprint


def test_compute_prompt_fingerprint_direct():
    rendered = RenderedPrompt(
        system="System prompt content",
        user="User prompt content"
    )
    budget = Budget(
        max_input_tokens_approx=4000,
        max_output_tokens=2000,
        soft_char_limit=16000,
        estimated_input_tokens=1000
    )
    fact_ids = ["fact_1", "fact_2"]

    fingerprint1 = compute_prompt_fingerprint(
        rendered=rendered,
        spec_key="intro",
        fact_ids=fact_ids,
        budget=budget
    )

    fingerprint2 = compute_prompt_fingerprint(
        rendered=rendered,
        spec_key="intro",
        fact_ids=fact_ids,
        budget=budget
    )

    assert fingerprint1 == fingerprint2
    assert len(fingerprint1) == 16


def test_fingerprint_fact_order_independent():
    rendered = RenderedPrompt(
        system="System prompt",
        user="User prompt"
    )
    budget = Budget(
        max_input_tokens_approx=4000,
        max_output_tokens=2000,
        soft_char_limit=16000,
        estimated_input_tokens=1000
    )

    fp1 = compute_prompt_fingerprint(
        rendered=rendered,
        spec_key="intro",
        fact_ids=["fact_1", "fact_2", "fact_3"],
        budget=budget
    )

    fp2 = compute_prompt_fingerprint(
        rendered=rendered,
        spec_key="intro",
        fact_ids=["fact_3", "fact_1", "fact_2"],
        budget=budget
    )

    assert fp1 == fp2


def test_prompt_version_is_set(sample_facts, sample_outline):
    context_pack = slice_for_section(
        section_key="intro",
        facts=sample_facts,
        outline=sample_outline,
        summaries=[],
        global_context="Test"
    )

    assert context_pack.prompt_version == "v1.0.0"
