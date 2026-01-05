from django.urls import path
from . import views
from . import pipeline_views

app_name = 'projects'

urlpatterns = [
    path('analyze/', views.create_analysis, name='create_analysis'),
    path('jobs/<uuid:job_id>/', views.get_job_status, name='job_status'),
    path('jobs/<uuid:job_id>/artifacts/', views.get_job_artifacts, name='job_artifacts'),
    path('jobs/<uuid:job_id>/run/', views.run_step, name='run_step'),

    path('documents/', views.create_document_view, name='create_document'),
    path('documents/<uuid:document_id>/', views.get_document, name='get_document'),
    path('documents/<uuid:document_id>/outline/', views.document_outline, name='document_outline'),
    path('documents/<uuid:document_id>/sections/', views.list_sections, name='list_sections'),
    path('documents/<uuid:document_id>/sections/<str:section_key>/', views.get_section, name='get_section'),
    path('documents/<uuid:document_id>/sections/<str:section_key>/generate/', views.generate_section, name='generate_section'),
    path('documents/<uuid:document_id>/sections/<str:section_key>/context-pack/', views.build_context_pack, name='build_context_pack'),
    path('documents/<uuid:document_id>/sections/<str:section_key>/latest/', views.section_latest, name='section_latest'),

    path('sections/', views.sections_registry, name='sections_registry'),

    path('documents/<uuid:document_id>/pipeline/run/', pipeline_views.run_pipeline, name='run_pipeline'),
    path('documents/<uuid:document_id>/pipeline/run-sync/', pipeline_views.run_pipeline_sync, name='run_pipeline_sync'),
    path('documents/<uuid:document_id>/pipeline/status/', pipeline_views.pipeline_status, name='pipeline_status'),
    path('documents/<uuid:document_id>/pipeline/draft/', pipeline_views.get_document_draft, name='get_document_draft'),
    path('documents/<uuid:document_id>/pipeline/toc/', pipeline_views.get_toc, name='get_toc'),
    path('documents/<uuid:document_id>/pipeline/quality/', pipeline_views.get_quality_report, name='get_quality_report'),
    path('documents/<uuid:document_id>/pipeline/edited/', pipeline_views.get_document_edited, name='get_document_edited'),
    path('documents/<uuid:document_id>/pipeline/glossary/', pipeline_views.get_glossary, name='get_glossary'),
    path('documents/<uuid:document_id>/pipeline/edit-plan/', pipeline_views.get_edit_plan, name='get_edit_plan'),

    path('pipeline/profiles/', pipeline_views.get_profiles, name='get_profiles'),
    path('pipeline/sections/', pipeline_views.get_pipeline_sections, name='get_pipeline_sections'),
    path('pipeline/test-document/', pipeline_views.create_test_document, name='create_test_document'),
    path('pipeline/run/', pipeline_views.run_pipeline_full, name='run_pipeline_full'),
]
