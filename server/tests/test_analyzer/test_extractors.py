import tempfile
from pathlib import Path

import pytest

from services.analyzer.extractors import (
    extract_django_models,
    extract_drf_endpoints,
    extract_pipeline_steps,
    extract_artifact_kinds,
)


class TestExtractDjangoModels:

    def test_extracts_basic_model(self, tmp_path):
        models_file = tmp_path / "models.py"
        models_file.write_text("""
from django.db import models

class Document(models.Model):
    title = models.CharField(max_length=255)
    status = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
""")

        models = extract_django_models(tmp_path)

        assert len(models) == 1
        assert models[0].name == "Document"
        assert len(models[0].fields) == 3
        field_names = [f["name"] for f in models[0].fields]
        assert "title" in field_names
        assert "status" in field_names
        assert "created_at" in field_names

    def test_extracts_foreign_key_relationships(self, tmp_path):
        models_file = tmp_path / "models.py"
        models_file.write_text("""
from django.db import models

class Project(models.Model):
    name = models.CharField(max_length=255)

class Document(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
""")

        models = extract_django_models(tmp_path)

        assert len(models) == 2
        doc_model = next(m for m in models if m.name == "Document")
        assert len(doc_model.relationships) == 1
        assert doc_model.relationships[0]["target"] == "Project"
        assert doc_model.relationships[0]["type"] == "ForeignKey"

    def test_extracts_choices_classes(self, tmp_path):
        models_file = tmp_path / "models.py"
        models_file.write_text("""
from django.db import models

class Document(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PUBLISHED = 'published', 'Published'

    status = models.CharField(max_length=20, choices=Status.choices)
""")

        models = extract_django_models(tmp_path)

        assert len(models) == 1
        assert "choices" in models[0].meta
        assert "Status" in models[0].meta["choices"]

    def test_ignores_non_model_files(self, tmp_path):
        (tmp_path / "views.py").write_text("from django.db import models")
        (tmp_path / "utils.py").write_text("import models")

        models = extract_django_models(tmp_path)
        assert len(models) == 0


class TestExtractDRFEndpoints:

    def test_extracts_api_view_functions(self, tmp_path):
        views_file = tmp_path / "views.py"
        views_file.write_text("""
from rest_framework.decorators import api_view
from rest_framework.response import Response

@api_view(['GET', 'POST'])
def list_documents(request):
    return Response({})

@api_view(['GET'])
def get_document(request, pk):
    return Response({})
""")

        endpoints = extract_drf_endpoints(tmp_path)

        assert len(endpoints) >= 2
        methods = [e.method for e in endpoints]
        assert "GET" in methods
        assert "POST" in methods

    def test_extracts_tags_from_extend_schema(self, tmp_path):
        views_file = tmp_path / "views.py"
        views_file.write_text("""
from rest_framework.decorators import api_view
from drf_spectacular.utils import extend_schema

@extend_schema(tags=["Documents"])
@api_view(['POST'])
def create_document(request):
    pass
""")

        endpoints = extract_drf_endpoints(tmp_path)

        assert len(endpoints) == 1
        assert endpoints[0].viewset == "Documents"

    def test_extracts_viewset_endpoints(self, tmp_path):
        views_file = tmp_path / "views.py"
        views_file.write_text("""
from rest_framework import viewsets
from rest_framework.decorators import action

class DocumentViewSet(viewsets.ModelViewSet):
    serializer_class = DocumentSerializer

    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        pass
""")

        endpoints = extract_drf_endpoints(tmp_path)

        assert len(endpoints) >= 1
        actions = [e.action for e in endpoints]
        assert "publish" in actions or "list" in actions


class TestExtractPipelineSteps:

    def test_extracts_ensure_functions(self, tmp_path):
        steps_dir = tmp_path / "services" / "pipeline" / "steps"
        steps_dir.mkdir(parents=True)

        (steps_dir / "outline.py").write_text("""
def ensure_outline(
    document_id,
    force=False
):
    kind = ArtifactKind.OUTLINE.value
    pass
""")

        (steps_dir / "section.py").write_text("""
def ensure_section(
    document_id,
    section_key
):
    kind = ArtifactKind.SECTION.value
    pass
""")

        steps = extract_pipeline_steps(tmp_path)

        assert len(steps) == 2
        names = [s.name for s in steps]
        assert "ensure_outline" in names
        assert "ensure_section" in names

    def test_extracts_artifact_kind(self, tmp_path):
        steps_dir = tmp_path / "services" / "pipeline" / "steps"
        steps_dir.mkdir(parents=True)

        (steps_dir / "quality.py").write_text("""
def ensure_quality_report(
    document_id,
    force=False
):
    kind = ArtifactKind.QUALITY_REPORT.value
    pass
""")

        steps = extract_pipeline_steps(tmp_path)

        assert len(steps) == 1
        assert steps[0].kind == "QUALITY_REPORT"


class TestExtractArtifactKinds:

    def test_extracts_enum_values(self, tmp_path):
        pipeline_dir = tmp_path / "services" / "pipeline"
        pipeline_dir.mkdir(parents=True)

        (pipeline_dir / "kinds.py").write_text("""
from enum import Enum

class ArtifactKind(str, Enum):
    OUTLINE = "outline:v1"
    SECTION = "section:{key}:v1"
    DOCUMENT_DRAFT = "document_draft:v1"
""")

        kinds = extract_artifact_kinds(tmp_path)

        assert len(kinds) == 3
        names = [k["name"] for k in kinds]
        assert "OUTLINE" in names
        assert "SECTION" in names
        assert "DOCUMENT_DRAFT" in names

        outline = next(k for k in kinds if k["name"] == "OUTLINE")
        assert outline["value"] == "outline:v1"
