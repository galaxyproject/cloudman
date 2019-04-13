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
urlpatterns = [
    url(r'^', include(router.urls)),
]
