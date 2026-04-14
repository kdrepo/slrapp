from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reviews', '0032_litreview_research_context'),
    ]

    operations = [
        migrations.AddField(
            model_name='reviewsection',
            name='notable_authors',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
