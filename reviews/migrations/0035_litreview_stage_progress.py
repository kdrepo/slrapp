from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reviews', '0034_litpaper'),
    ]

    operations = [
        migrations.AddField(
            model_name='litreview',
            name='stage_progress',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
