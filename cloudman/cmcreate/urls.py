"""CloudMan Create URL configuration."""

from django.conf.urls import include
from django.conf.urls import url

from cmcreate import views
from .drf_routers import HybridDefaultRouter

router = HybridDefaultRouter()
router.register(r'infrastructure', views.InfrastructureView,
                base_name='infrastructure')

urlpatterns = [
    url(r'v1/', include(router.urls)),
    url(r'v1/auth/', include('rest_framework.urls',
                             namespace='rest_framework'))
]
