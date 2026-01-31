from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventory_api', '0008_monitoring_rawmetric_trackedvm'),
    ]

    operations = [
        migrations.CreateModel(
            name='ComputedMetric',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=100)),
                ('value', models.FloatField()),
                ('unit', models.CharField(blank=True, max_length=20)),
                ('window', models.CharField(max_length=20)),
                ('timestamp', models.DateTimeField()),
                ('labels', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='metrics_computed', to='inventory_api.device')),
            ],
            options={
                'verbose_name': 'Вычисленная метрика',
                'verbose_name_plural': 'Вычисленные метрики',
                'ordering': ['-timestamp'],
            },
        ),
        migrations.AddIndex(
            model_name='computedmetric',
            index=models.Index(fields=['device', 'code', '-timestamp'], name='inventory_a_device__f5590f_idx'),
        ),
        migrations.AddIndex(
            model_name='computedmetric',
            index=models.Index(fields=['timestamp'], name='inventory_a_timesta_18a3d0_idx'),
        ),
    ]

