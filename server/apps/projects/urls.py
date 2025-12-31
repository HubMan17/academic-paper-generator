from django.urls import path
from . import views

app_name = 'projects'

urlpatterns = [
    path('analyze/', views.create_analysis, name='create_analysis'),
    path('jobs/<uuid:job_id>/', views.get_job_status, name='job_status'),
    path('jobs/<uuid:job_id>/artifacts/', views.get_job_artifacts, name='job_artifacts'),
]
