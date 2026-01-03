from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0004_documentartifact'),
    ]

    operations = [
        migrations.AddField(
            model_name='document',
            name='params',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='document',
            name='outline_current',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='as_current_outline_for_documents', to='projects.documentartifact'),
        ),
    ]
