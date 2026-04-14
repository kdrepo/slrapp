from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reviews', '0031_litreview_research_questions'),
    ]

    operations = [
        migrations.AddField(
            model_name='litreview',
            name='research_context',
            field=models.TextField(blank=True),
        ),
    ]
