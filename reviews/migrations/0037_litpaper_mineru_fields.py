from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reviews', '0036_litpaper_citation_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='litpaper',
            name='mineru_batch_id',
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name='litpaper',
            name='mineru_error',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='litpaper',
            name='mineru_markdown',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='litpaper',
            name='mineru_parsed',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='litpaper',
            name='mineru_status',
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name='litpaper',
            name='processed_pdf_mineru',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='litpaper',
            name='ref_delete_done',
            field=models.BooleanField(default=False),
        ),
    ]
