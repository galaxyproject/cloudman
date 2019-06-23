"""CloudMan Create URL configuration."""

from django.conf.urls import include
from django.conf.urls import url

from . import views
from helmsman import views as helmsman_views
from djcloudbridge.drf_routers import HybridDefaultRouter
from djcloudbridge.drf_routers import HybridNestedRouter


router = HybridDefaultRouter()
router.register(r'projects', views.ProjectViewSet,
                base_name='projects')

project_router = HybridNestedRouter(router, r'projects',
                                    lookup='project')
project_router.register(r'charts', views.ProjectChartViewSet,
                        base_name='chart')

cluster_regex_pattern = r'^'
urlpatterns = [
    url(r'^', include(router.urls)),
    url(cluster_regex_pattern, include(project_router.urls))
]
