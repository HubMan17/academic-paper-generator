from django.urls import path

from . import views

urlpatterns = [
    path('test/', views.test_analyzer_page, name='test_analyzer'),
]

api_v1_urlpatterns = [
    path('analyzer/analyze/', views.analyze_repository_api, name='analyze_repository'),
]
