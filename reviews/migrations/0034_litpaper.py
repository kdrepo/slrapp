from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('reviews', '0033_reviewsection_notable_authors'),
    ]

    operations = [
        migrations.CreateModel(
            name='LitPaper',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=500)),
                ('authors', models.TextField(blank=True)),
                ('year', models.IntegerField(blank=True, null=True)),
                ('source', models.CharField(blank=True, max_length=255)),
                ('doi', models.CharField(blank=True, db_index=True, max_length=255)),
                ('url', models.URLField(blank=True)),
                ('pdf_link', models.URLField(blank=True)),
                ('origin', models.CharField(choices=[('ris_upload', 'RIS Upload'), ('excel_upload', 'Excel Upload'), ('pdf_upload', 'PDF Upload')], max_length=20)),
                ('excel_row_index', models.IntegerField(blank=True, null=True)),
                ('pdf_path', models.FileField(blank=True, upload_to='lit_papers/pdfs/')),
                ('fulltext_retrieved', models.BooleanField(default=False)),
                ('pdf_source', models.CharField(blank=True, max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('review', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='papers', to='reviews.litreview')),
            ],
            options={
                'ordering': ['id'],
            },
        ),
    ]
