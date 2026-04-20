from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('reviews', '0042_paper_full_text_tccm'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='review',
            name='theoretical_lens',
        ),
    ]

