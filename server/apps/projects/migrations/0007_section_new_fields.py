from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0006_section_rename_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='section',
            name='last_artifact',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='as_last_for_sections', to='projects.documentartifact'),
        ),
        migrations.AddField(
            model_name='section',
            name='last_error',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AlterField(
            model_name='section',
            name='version',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='section',
            name='status',
            field=models.CharField(
                choices=[
                    ('idle', 'Idle'),
                    ('queued', 'Queued'),
                    ('running', 'Running'),
                    ('success', 'Success'),
                    ('failed', 'Failed'),
                    ('pending', 'Pending'),
                    ('generating', 'Generating'),
                    ('ready', 'Ready'),
                    ('error', 'Error'),
                ],
                default='idle',
                max_length=20
            ),
        ),
    ]
