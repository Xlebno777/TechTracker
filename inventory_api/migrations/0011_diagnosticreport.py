from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventory_api', '0010_agentstatus'),
    ]

    operations = [
        migrations.CreateModel(
            name='DiagnosticReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('summary', models.TextField()),
                ('severity', models.CharField(choices=[('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')], default='low', max_length=20)),
                ('issues', models.JSONField(blank=True, default=list)),
                ('recommendations', models.JSONField(blank=True, default=list)),
                ('payload', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='diagnostic_reports', to='inventory_api.device')),
            ],
            options={
                'verbose_name': 'Диагностический отчет',
                'verbose_name_plural': 'Диагностические отчеты',
                'ordering': ['-created_at'],
            },
        ),
    ]
