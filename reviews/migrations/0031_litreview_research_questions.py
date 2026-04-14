from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reviews', '0030_litreview_reviewsection'),
    ]

    operations = [
        migrations.AddField(
            model_name='litreview',
            name='research_questions',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
