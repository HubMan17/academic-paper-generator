from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0008_section_status_data_migration'),
    ]

    operations = [
        migrations.AlterField(
            model_name='section',
            name='key',
            field=models.CharField(max_length=50),
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
                ],
                default='idle',
                max_length=20
            ),
        ),
    ]
