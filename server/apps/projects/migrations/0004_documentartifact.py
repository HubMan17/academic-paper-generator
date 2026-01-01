import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0003_artifact_schema_version_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='DocumentArtifact',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('job_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('kind', models.CharField(choices=[('outline', 'Outline JSON'), ('section_text', 'Section Text'), ('section_summary', 'Section Summary')], max_length=32)),
                ('format', models.CharField(choices=[('json', 'JSON'), ('markdown', 'Markdown'), ('text', 'Text')], max_length=16)),
                ('data_json', models.JSONField(blank=True, null=True)),
                ('content_text', models.TextField(blank=True, null=True)),
                ('meta', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('document', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='doc_artifacts', to='projects.document')),
                ('section', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='doc_artifacts', to='projects.section')),
            ],
            options={
                'db_table': 'document_artifact',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='documentartifact',
            index=models.Index(fields=['document', 'kind', 'created_at'], name='document_ar_documen_7e2a1b_idx'),
        ),
        migrations.AddIndex(
            model_name='documentartifact',
            index=models.Index(fields=['section', 'kind', 'created_at'], name='document_ar_section_b4c3e2_idx'),
        ),
    ]
