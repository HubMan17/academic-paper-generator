from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0005_document_params_outline'),
    ]

    operations = [
        migrations.RenameField(
            model_name='section',
            old_name='content',
            new_name='text_current',
        ),
        migrations.RenameField(
            model_name='section',
            old_name='summary',
            new_name='summary_current',
        ),
    ]
