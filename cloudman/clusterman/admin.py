"""Models exposed via Django Admin."""
from django.contrib import admin
import nested_admin

from . import models


class CMClusterNodeAdmin(nested_admin.NestedStackedInline):
    model = models.CMClusterNode
    extra = 0


@admin.register(models.CMCluster)
class CMClusterAdmin(nested_admin.NestedModelAdmin):
    inlines = [CMClusterNodeAdmin]
    ordering = ('added',)
