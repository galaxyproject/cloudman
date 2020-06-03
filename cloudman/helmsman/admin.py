from django.contrib import admin

from . import models


@admin.register(models.HMInstallTemplate)
class HMInstallTemplateAdmin(admin.ModelAdmin):
    ordering = ('added',)
