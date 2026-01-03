import pytest
from uuid import uuid4

from django.test import TestCase

from apps.projects.models import Project, AnalysisRun, Artifact, Document, Section, DocumentArtifact
from services.pipeline import (
    DocumentRunner,
    get_success_artifact,
    ArtifactKind,
    get_all_section_keys,
)


@pytest.fixture
def setup_document(db):
    project = Project.objects.create(repo_url="https://github.com/test/repo")
    analysis_run = AnalysisRun.objects.create(
        project=project,
        status=AnalysisRun.Status.SUCCESS,
    )

    Artifact.objects.create(
        analysis_run=analysis_run,
        kind=Artifact.Kind.FACTS,
        data={
            "repo": {
                "url": "https://github.com/test/repo",
                "commit": "abc123",
                "detected_at": "2024-01-01T00:00:00Z",
            },
            "languages": [{"name": "Python", "ratio": 0.8, "lines_of_code": 1000}],
            "frameworks": [{"name": "Django", "type": "backend", "version": "5.0"}],
            "architecture": {
                "type": "layered",
                "layers": ["api", "services"],
                "evidence": [{"path": "app/api.py"}],
            },
            "modules": [{"path": "app/main.py", "type": "module", "name": "main"}],
            "dependencies": {"backend": [{"name": "django", "version": "5.0"}]},
        }
    )

    document = Document.objects.create(
        analysis_run=analysis_run,
        type=Document.Type.COURSE,
        language="ru-RU",
        target_pages=40,
        params={"title": "Test Document"},
        status=Document.Status.DRAFT,
    )

    sections = []
    for i, key in enumerate(get_all_section_keys()):
        sections.append(Section(
            document=document,
            key=key,
            title=f"Section {key}",
            order=i,
            status=Section.Status.IDLE,
        ))
    Section.objects.bulk_create(sections)

    return document


@pytest.mark.django_db
class TestDocumentRunner:
    def test_run_full_creates_all_artifacts(self, setup_document):
        document = setup_document
        runner = DocumentRunner(
            document_id=document.id,
            profile="default",
            mock_mode=True,
        )

        result = runner.run_full(job_id=uuid4(), force=False)

        assert result.success is True
        assert len(result.errors) == 0

        outline = get_success_artifact(document.id, ArtifactKind.OUTLINE.value)
        assert outline is not None

        for key in get_all_section_keys():
            context_pack = get_success_artifact(document.id, ArtifactKind.context_pack(key))
            section = get_success_artifact(document.id, ArtifactKind.section(key))
            summary = get_success_artifact(document.id, ArtifactKind.section_summary(key))

            assert context_pack is not None, f"Missing context_pack for {key}"
            assert section is not None, f"Missing section for {key}"
            assert summary is not None, f"Missing summary for {key}"

        draft = get_success_artifact(document.id, ArtifactKind.DOCUMENT_DRAFT.value)
        toc = get_success_artifact(document.id, ArtifactKind.TOC.value)
        quality = get_success_artifact(document.id, ArtifactKind.QUALITY_REPORT.value)

        assert draft is not None
        assert toc is not None
        assert quality is not None

    def test_run_full_uses_cache(self, setup_document):
        document = setup_document
        runner = DocumentRunner(
            document_id=document.id,
            profile="default",
            mock_mode=True,
        )

        result1 = runner.run_full(job_id=uuid4(), force=False)
        assert result1.success is True

        created_count = len(result1.artifacts_created)
        assert created_count > 0

        result2 = runner.run_full(job_id=uuid4(), force=False)
        assert result2.success is True

        assert len(result2.artifacts_created) == 0
        assert len(result2.artifacts_cached) > 0

    def test_run_section_regenerates_with_force(self, setup_document):
        document = setup_document
        runner = DocumentRunner(
            document_id=document.id,
            profile="default",
            mock_mode=True,
        )

        result1 = runner.run_full(job_id=uuid4(), force=False)
        assert result1.success is True

        result2 = runner.run_section(
            section_key="intro",
            job_id=uuid4(),
            force=True,
        )

        assert result2.success is True
        assert "section:intro:v1" in result2.artifacts_created


@pytest.mark.django_db
class TestArtifactKind:
    def test_section_kind_formatting(self):
        assert ArtifactKind.section("intro") == "section:intro:v1"
        assert ArtifactKind.section("architecture") == "section:architecture:v1"

    def test_context_pack_kind_formatting(self):
        assert ArtifactKind.context_pack("intro") == "context_pack:intro:v1"

    def test_section_summary_kind_formatting(self):
        assert ArtifactKind.section_summary("intro") == "section_summary:intro:v1"


@pytest.mark.django_db
class TestProfiles:
    def test_get_profile_default(self):
        from services.pipeline import get_profile

        profile = get_profile("default")
        assert profile.name == "default"
        assert profile.target_words_multiplier == 1.0

    def test_get_profile_fast(self):
        from services.pipeline import get_profile

        profile = get_profile("fast")
        assert profile.name == "fast"
        assert profile.target_words_multiplier < 1.0

    def test_get_profile_heavy(self):
        from services.pipeline import get_profile

        profile = get_profile("heavy")
        assert profile.name == "heavy"
        assert profile.target_words_multiplier > 1.0

    def test_get_profile_invalid(self):
        from services.pipeline import get_profile

        with pytest.raises(ValueError):
            get_profile("invalid_profile")
