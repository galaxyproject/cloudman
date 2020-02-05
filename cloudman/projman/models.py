from django.conf import settings
from django.db import models


class CMProject(models.Model):
    """CloudMan project details."""
    # Automatically add timestamps when object is created
    added = models.DateTimeField(auto_now_add=True)
    # Automatically add timestamps when object is updated
    updated = models.DateTimeField(auto_now=True)
    # Each project corresponds to a k8s namespace and therefore, must be unique
    name = models.CharField(max_length=60, unique=True)
    namespace = models.SlugField(max_length=253, unique=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                              null=False)

    class Meta:
        verbose_name = "Project"
        verbose_name_plural = "Projects"

    def __str__(self):
        return "{0} ({1})".format(self.name, self.id)
