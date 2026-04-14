from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reviews', '0037_litpaper_mineru_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='litpaper',
            name='per_paper_extraction',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='litpaper',
            name='per_paper_extraction_error',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='litpaper',
            name='per_paper_extraction_status',
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name='litpaper',
            name='per_paper_extraction_updated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='litpaper',
            name='per_paper_quality_category',
            field=models.CharField(blank=True, max_length=1),
        ),
    ]
