from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('reviews', '0029_paper_title_screening_confidence_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LitReview',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('research_question', models.TextField()),
                ('target_word_count', models.IntegerField()),
                ('total_words_allocated', models.IntegerField(default=0)),
                ('review_goal', models.TextField(blank=True)),
                ('gap_statement', models.TextField(blank=True)),
                ('section_order_rationale', models.TextField(blank=True)),
                ('final_prose', models.TextField(blank=True)),
                ('status', models.CharField(choices=[('planning', 'Planning'), ('searching', 'Searching'), ('extracting', 'Extracting'), ('writing', 'Writing'), ('done', 'Done')], default='planning', max_length=16)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='lit_reviews', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='ReviewSection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('number', models.IntegerField()),
                ('title', models.CharField(max_length=255)),
                ('type', models.CharField(choices=[('foundation', 'Foundation'), ('debate', 'Debate'), ('recent', 'Recent'), ('gap', 'Gap')], max_length=16)),
                ('purpose', models.TextField(blank=True)),
                ('what_to_look_for', models.TextField(blank=True)),
                ('search_keywords', models.JSONField(blank=True, default=list)),
                ('target_paper_count', models.CharField(blank=True, max_length=64)),
                ('leads_to', models.TextField(blank=True)),
                ('word_count_target', models.IntegerField(default=0)),
                ('prose', models.TextField(blank=True)),
                ('review', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sections', to='reviews.litreview')),
            ],
            options={
                'ordering': ['number', 'id'],
            },
        ),
        migrations.AddConstraint(
            model_name='reviewsection',
            constraint=models.UniqueConstraint(fields=('review', 'number'), name='unique_lit_review_section_number'),
        ),
    ]
