"""CloudMan Create URL configuration."""

from django.conf.urls import include
from django.conf.urls import url

from . import views
from helmsman import views as helmsman_views
from djcloudbridge.drf_routers import HybridDefaultRouter
from djcloudbridge.drf_routers import HybridNestedRouter


router = HybridDefaultRouter()
router.register(r'clusters', views.ClusterViewSet,
                base_name='clusters')
router.register(r'repositories', helmsman_views.ChartRepoViewSet,
                base_name='repositories')
router.register(r'charts', helmsman_views.ChartViewSet,
                base_name='charts')

cluster_router = HybridNestedRouter(router, r'clusters',
                                    lookup='cluster')
cluster_router.register(r'nodes', views.ClusterNodeViewSet,
                        base_name='node')

cluster_regex_pattern = r''
urlpatterns = [
    url(r'', include(router.urls)),
    url(cluster_regex_pattern, include(cluster_router.urls))
]
