from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory_api', '0011_diagnosticreport'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='diagnosticreport',
            index=models.Index(fields=['device', 'severity', '-created_at'], name='inventory_a_device__f1977f_idx'),
        ),
        migrations.AddIndex(
            model_name='diagnosticreport',
            index=models.Index(fields=['severity', '-created_at'], name='inventory_a_severit_0e3736_idx'),
        ),
    ]
