from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reviews', '0038_litpaper_per_paper_extraction_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='litpaper',
            name='section_assignment_error',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='litpaper',
            name='section_assignment_status',
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name='litpaper',
            name='section_assignment_updated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='LitPaperAssignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('assignment_confidence', models.CharField(blank=True, max_length=16)),
                ('reason', models.TextField(blank=True)),
                ('how_to_use', models.TextField(blank=True)),
                ('also_relevant_to', models.JSONField(blank=True, default=list)),
                ('flag', models.CharField(blank=True, max_length=64)),
                ('raw_payload', models.JSONField(blank=True, default=dict)),
                ('assigned_at', models.DateTimeField(auto_now=True)),
                ('paper', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='section_assignments', to='reviews.litpaper')),
                ('review', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='paper_assignments', to='reviews.litreview')),
                ('section', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='paper_assignments', to='reviews.reviewsection')),
            ],
            options={
                'ordering': ['id'],
            },
        ),
        migrations.AddConstraint(
            model_name='litpaperassignment',
            constraint=models.UniqueConstraint(fields=('review', 'paper'), name='unique_lit_review_paper_assignment'),
        ),
    ]
