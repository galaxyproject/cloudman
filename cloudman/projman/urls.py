"""CloudMan Create URL configuration."""

from django.urls import include
from django.urls import re_path

from . import views

from djcloudbridge.drf_routers import HybridDefaultRouter
from djcloudbridge.drf_routers import HybridNestedRouter


router = HybridDefaultRouter()
router.register(r'projects', views.ProjectViewSet,
                basename='projects')

project_router = HybridNestedRouter(router, r'projects',
                                    lookup='project')
project_router.register(r'charts', views.ProjectChartViewSet,
                        basename='chart')

app_name = "projman"

cluster_regex_pattern = r'^'
urlpatterns = [
    re_path(r'^', include(router.urls)),
    re_path(cluster_regex_pattern, include(project_router.urls))
]
