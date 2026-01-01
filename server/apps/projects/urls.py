from django.urls import path
from . import views

app_name = 'projects'

urlpatterns = [
    path('analyze/', views.create_analysis, name='create_analysis'),
    path('jobs/<uuid:job_id>/', views.get_job_status, name='job_status'),
    path('jobs/<uuid:job_id>/artifacts/', views.get_job_artifacts, name='job_artifacts'),

    path('documents/', views.create_document_view, name='create_document'),
    path('documents/<uuid:document_id>/', views.get_document, name='get_document'),
    path('documents/<uuid:document_id>/outline/', views.document_outline, name='document_outline'),
    path('documents/<uuid:document_id>/sections/', views.list_sections, name='list_sections'),
    path('documents/<uuid:document_id>/sections/<str:section_key>/', views.get_section, name='get_section'),
    path('documents/<uuid:document_id>/sections/<str:section_key>/generate/', views.generate_section, name='generate_section'),
]
