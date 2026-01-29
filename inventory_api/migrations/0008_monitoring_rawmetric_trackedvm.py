from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventory_api', '0007_alter_printjob_timestamp'),
    ]

    operations = [
        migrations.CreateModel(
            name='MonitoringSetting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('retention_days', models.PositiveIntegerField(default=365)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('device', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='monitoring_settings', to='inventory_api.device')),
            ],
            options={
                'verbose_name': 'Настройки мониторинга',
                'verbose_name_plural': 'Настройки мониторинга',
            },
        ),
        migrations.CreateModel(
            name='RawMetric',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=100)),
                ('value', models.FloatField()),
                ('unit', models.CharField(blank=True, max_length=20)),
                ('timestamp', models.DateTimeField()),
                ('labels', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='metrics_raw', to='inventory_api.device')),
            ],
            options={
                'verbose_name': 'Сырая метрика',
                'verbose_name_plural': 'Сырые метрики',
                'ordering': ['-timestamp'],
            },
        ),
        migrations.CreateModel(
            name='TrackedVM',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, unique=True)),
                ('status', models.CharField(choices=[('running', 'Включена'), ('off', 'Выключена'), ('paused', 'Пауза'), ('saved', 'Сохранена'), ('unknown', 'Неизвестно')], default='unknown', max_length=20)),
                ('cpu_usage', models.FloatField(blank=True, null=True)),
                ('memory_usage', models.FloatField(blank=True, null=True)),
                ('uptime_seconds', models.BigIntegerField(blank=True, null=True)),
                ('last_seen', models.DateTimeField(blank=True, null=True)),
                ('is_enabled', models.BooleanField(default=True)),
                ('host_device', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tracked_vms', to='inventory_api.device')),
            ],
            options={
                'verbose_name': 'Отслеживаемая ВМ',
                'verbose_name_plural': 'Отслеживаемые ВМ',
                'ordering': ['name'],
            },
        ),
        migrations.AddIndex(
            model_name='rawmetric',
            index=models.Index(fields=['device', 'code', '-timestamp'], name='inventory_a_device__70bfa9_idx'),
        ),
        migrations.AddIndex(
            model_name='rawmetric',
            index=models.Index(fields=['timestamp'], name='inventory_a_timesta_0fc879_idx'),
        ),
    ]
