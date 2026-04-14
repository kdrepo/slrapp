from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reviews', '0035_litreview_stage_progress'),
    ]

    operations = [
        migrations.AddField(
            model_name='litpaper',
            name='citation_apa',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='litpaper',
            name='citation_error',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='litpaper',
            name='citation_source',
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name='litpaper',
            name='citation_status',
            field=models.CharField(blank=True, max_length=32),
        ),
    ]
