"""CloudMan Create URL configuration."""

from django.conf.urls import include
from django.conf.urls import url

from . import views
from djcloudbridge.drf_routers import HybridDefaultRouter
from djcloudbridge.drf_routers import HybridNestedRouter


router = HybridDefaultRouter()
router.register(r'clusters', views.ClusterViewSet,
                basename='clusters')

cluster_router = HybridNestedRouter(router, r'clusters',
                                    lookup='cluster')
cluster_router.register(r'nodes', views.ClusterNodeViewSet,
                        basename='node')
cluster_router.register(r'autoscalers', views.ClusterAutoScalerViewSet,
                        basename='autoscaler')
cluster_router.register(r'signals/scaleup', views.ClusterScaleUpSignalView,
                        basename='scaleupsignal')
cluster_router.register(r'signals/scaledown', views.ClusterScaleDownSignalView,
                        basename='scaledownsignal')


app_name = "clusterman"

cluster_regex_pattern = r'^'
urlpatterns = [
    url(r'^', include(router.urls)),
    url(cluster_regex_pattern, include(cluster_router.urls))
]
