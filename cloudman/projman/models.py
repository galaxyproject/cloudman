from django.db import models


class CMProject(models.Model):
    """CloudMan project details."""
    # Automatically add timestamps when object is created
    added = models.DateTimeField(auto_now_add=True)
    # Automatically add timestamps when object is updated
    updated = models.DateTimeField(auto_now=True)
    # Each project corresponds to a k8s namespace and therefore, must be unique
    name = models.CharField(max_length=60, unique=True)

    class Meta:
        verbose_name = "Project"
        verbose_name_plural = "Projects"
