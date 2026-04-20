from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reviews', '0040_alter_paper_title_screening_decision'),
    ]

    operations = [
        migrations.AddField(
            model_name='review',
            name='theoretical_lens',
            field=models.TextField(blank=True),
        ),
    ]

