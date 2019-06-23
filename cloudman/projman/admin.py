"""Models exposed via Django Admin."""
from django.contrib import admin

from . import models


@admin.register(models.CMProject)
class CMProjectAdmin(admin.ModelAdmin):
    ordering = ('added',)
