"""CloudMan Create URL configuration."""

from django.conf.urls import include
from django.conf.urls import url

from . import views
from djcloudbridge.drf_routers import HybridDefaultRouter


router = HybridDefaultRouter()
router.register(r'repositories', views.ChartRepoViewSet,
                base_name='repositories')
router.register(r'charts', views.ChartViewSet,
                base_name='charts')
router.register(r'namespaces', views.NamespaceViewSet,
                base_name='namespaces')
router.register(r'install_templates', views.InstallTemplatesViewSet,
                base_name='install_templates')

app_name = "helmsman"

urlpatterns = [
    url(r'^', include(router.urls)),
]
