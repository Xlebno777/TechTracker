from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory_api', '0011_diagnosticreport'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='diagnosticreport',
            index=models.Index(fields=['device', 'severity', '-created_at'], name='inventory_d_device__a9a0c0_idx'),
        ),
        migrations.AddIndex(
            model_name='diagnosticreport',
            index=models.Index(fields=['severity', '-created_at'], name='inventory_d_severit_b1da8f_idx'),
        ),
    ]
