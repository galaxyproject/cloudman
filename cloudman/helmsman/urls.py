"""CloudMan Create URL configuration."""

from django.urls import include
from django.urls import re_path

from . import views
from djcloudbridge.drf_routers import HybridDefaultRouter


router = HybridDefaultRouter()
router.register(r'repositories', views.ChartRepoViewSet,
                basename='repositories')
router.register(r'charts', views.ChartViewSet,
                basename='charts')
router.register(r'namespaces', views.NamespaceViewSet,
                basename='namespaces')
router.register(r'install_templates', views.InstallTemplatesViewSet,
                basename='install_templates')

app_name = "helmsman"

urlpatterns = [
    re_path(r'^', include(router.urls)),
]
