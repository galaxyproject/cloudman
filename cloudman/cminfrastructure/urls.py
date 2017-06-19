"""CloudMan Create URL configuration."""

from django.conf.urls import include
from django.conf.urls import url

from cminfrastructure import views
from .drf_routers import HybridDefaultRouter
from .drf_routers import HybridNestedRouter
from .drf_routers import HybridSimpleRouter

router = HybridDefaultRouter()
router.register(r'infrastructure', views.InfrastructureView,
                base_name='infrastructure')

infra_router = HybridSimpleRouter()
infra_router.register(r'clouds', views.CloudViewSet, base_name='cloud')

cloud_router = HybridNestedRouter(infra_router, r'clouds', lookup='cloud')
#cloud_router.register(r'nodes', views.CloudNodeViewSet, base_name='node')

#node_router = HybridNestedRouter(cloud_router, r'instances', lookup='node')
#node_router.register(r'tasks', views.CloudNodeTaskViewSet, base_name='tasks')

cloud_router.register(r'instances', views.CloudNodeViewSet,
                      base_name='node')
node_router = HybridNestedRouter(cloud_router, r'instances', lookup='node')
node_router.register(r'tasks', views.CloudNodeTaskViewSet, base_name='nodetask')


infrastructure_regex_pattern = r'infrastructure/'
urlpatterns = [
    url(r'', include(router.urls)),
    url(infrastructure_regex_pattern, include(infra_router.urls)),
    url(infrastructure_regex_pattern, include(cloud_router.urls)),
    url(infrastructure_regex_pattern, include(node_router.urls)),
    url(r'', include('rest_framework.urls',
                     namespace='rest_framework'))
]
