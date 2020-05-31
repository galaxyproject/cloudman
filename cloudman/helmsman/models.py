from django.conf import settings
from django.db import models


class HMInstallTemplate(models.Model):
    """CloudMan project details."""
    # Automatically add timestamps when object is created
    added = models.DateTimeField(auto_now_add=True)
    # Automatically add timestamps when object is updated
    updated = models.DateTimeField(auto_now=True)
    # Each project corresponds to a k8s namespace and therefore, must be unique
    name = models.CharField(max_length=60, unique=True)
    repo = models.SlugField(max_length=60)
    chart = models.SlugField(max_length=60)
    chart_version = models.CharField(max_length=60, blank=True, null=True)
    template = models.TextField(blank=True, null=True)
    context = models.TextField(blank=True, null=True)
    display_name = models.TextField(blank=True, null=True)
    summary = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    maintainers = models.TextField(blank=True, null=True)
    info_url = models.TextField(blank=True, null=True)
    icon_url = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Install Template"
        verbose_name_plural = "Install Templates"

    def __str__(self):
        return "{0} ({1})".format(self.name, self.id)
