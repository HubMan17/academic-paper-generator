from django.urls import path

from . import views

urlpatterns = [
    path('test/', views.test_page, name='test_page'),
    path('test/analyzer/', views.test_analyzer_page, name='test_analyzer'),
    path('test/pipeline/', views.test_pipeline_page, name='test_pipeline'),
    path('dev/pipeline/', views.dev_pipeline_page, name='dev_pipeline'),
]

api_v1_urlpatterns = [
    path('analyzer/analyze/', views.analyze_repository_api, name='analyze_repository'),
    path('llm/text/', views.llm_generate_text_api, name='llm_generate_text'),
    path('llm/json/', views.llm_generate_json_api, name='llm_generate_json'),
    path('llm/stats/', views.llm_stats_api, name='llm_stats'),
    path('llm/clear/', views.llm_clear_cache_api, name='llm_clear_cache'),
    path('prompting/slice/', views.prompting_slice_api, name='prompting_slice'),
]
