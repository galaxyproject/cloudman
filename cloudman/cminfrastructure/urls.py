"""CloudMan Create URL configuration."""

from django.conf.urls import include
from django.conf.urls import url

from cminfrastructure import views
from .drf_routers import HybridDefaultRouter

router = HybridDefaultRouter()
router.register(r'infrastructure', views.InfrastructureView,
                base_name='infrastructure')

urlpatterns = [
    url(r'', include(router.urls)),
    url(r'', include('rest_framework.urls',
                     namespace='rest_framework'))
]
