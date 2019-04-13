"""
CloudMan URL Configuration.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.11/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls import include
from django.conf.urls import url
from rest_framework.schemas import get_schema_view

schema_view = get_schema_view(title='CloudMan API', url=settings.REST_SCHEMA_BASE_URL,
                              urlconf='cloudman.urls')

urlpatterns = [
    url(r'^cloudlaunch/', include('cloudlaunchserver.urls')),
    url(r'^api/v1/', include('cmcluster.urls')),
    url(r'^api/v1/schema/$', schema_view),
    url(r'^openid/', include('djangooidc.urls')),
]

# Uncomment to have Gunicorn serve static content (dev only)
# Also run: python manage.py collectstatic
# from django.contrib.staticfiles.urls import staticfiles_urlpatterns
# urlpatterns += staticfiles_urlpatterns()
