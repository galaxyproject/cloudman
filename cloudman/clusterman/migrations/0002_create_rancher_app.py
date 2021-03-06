# Generated by Django 2.0.5 on 2018-05-21 13:23
import os
from django.db import migrations
from django.core import serializers
from django.core.management import call_command


# based on: https://stackoverflow.com/a/39743581/10971151
def import_data(apps, schema_editor, filename):
    # Save the old _get_model() function
    old_get_model = serializers.python._get_model

    # Define new _get_model() function here, which utilizes the apps argument
    # to get the historical version of a model.
    def _get_model(model_identifier):
        try:
            return apps.get_model(model_identifier)
        except (LookupError, TypeError):
            raise serializers.base.DeserializationError(
                "Invalid model identifier: '%s'" % model_identifier)

    # Replace the _get_model() function, so loaddata can utilize it.
    serializers.python._get_model = _get_model

    try:
        # Call loaddata command
        call_command('loaddata', filename, app_label='clusterman')
    finally:
        # Restore old _get_model() function
        serializers.python._get_model = old_get_model


def import_rancher_app(apps, schema_editor):
    import_data(apps, schema_editor, 'rancher_app_def.json')


class Migration(migrations.Migration):

    dependencies = [
        ('clusterman', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(import_rancher_app)
    ]
