"""CloudMan Create URL configuration."""

from django.conf.urls import include
from django.conf.urls import url

from cmcluster import views
from djcloudbridge.drf_routers import HybridDefaultRouter
from djcloudbridge.drf_routers import HybridNestedRouter


router = HybridDefaultRouter()
router.register(r'clusters', views.ClusterViewSet,
                base_name='clusters')

cluster_router = HybridNestedRouter(router, r'clusters',
                                    lookup='cluster')
cluster_router.register(r'nodes', views.ClusterNodeViewSet,
                        base_name='node')

cluster_regex_pattern = r''
urlpatterns = [
    url(r'', include(router.urls)),
    url(cluster_regex_pattern, include(cluster_router.urls))
]
