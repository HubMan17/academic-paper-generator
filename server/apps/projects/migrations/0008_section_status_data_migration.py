from django.db import migrations


def convert_status_forward(apps, schema_editor):
    Section = apps.get_model('projects', 'Section')
    status_mapping = {
        'pending': 'idle',
        'generating': 'running',
        'ready': 'success',
        'error': 'failed',
    }
    for old_status, new_status in status_mapping.items():
        Section.objects.filter(status=old_status).update(status=new_status)


def convert_status_backward(apps, schema_editor):
    Section = apps.get_model('projects', 'Section')
    status_mapping = {
        'idle': 'pending',
        'running': 'generating',
        'success': 'ready',
        'failed': 'error',
    }
    for old_status, new_status in status_mapping.items():
        Section.objects.filter(status=old_status).update(status=new_status)


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0007_section_new_fields'),
    ]

    operations = [
        migrations.RunPython(convert_status_forward, convert_status_backward),
    ]
