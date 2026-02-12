from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventory_api', '0012_diagnosticreport_indexes'),
    ]

    operations = [
        migrations.CreateModel(
            name='NetworkPath',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('enabled', models.BooleanField(default=True)),
                ('interval_sec', models.PositiveIntegerField(default=60)),
                ('timeout_sec', models.PositiveIntegerField(default=3)),
                ('packet_count', models.PositiveIntegerField(default=1)),
                ('fail_threshold', models.PositiveIntegerField(default=3)),
                ('recover_threshold', models.PositiveIntegerField(default=2)),
                ('last_state', models.CharField(choices=[('unknown', 'Unknown'), ('up', 'Up'), ('down', 'Down')], default='unknown', max_length=20)),
                ('consecutive_failures', models.PositiveIntegerField(default=0)),
                ('consecutive_successes', models.PositiveIntegerField(default=0)),
                ('last_checked_at', models.DateTimeField(blank=True, null=True)),
                ('last_latency_ms', models.FloatField(blank=True, null=True)),
                ('last_packet_loss_pct', models.FloatField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('dst_device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='network_paths_dst', to='inventory_api.device')),
                ('src_device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='network_paths_src', to='inventory_api.device')),
            ],
            options={
                'verbose_name': 'Сетевой путь',
                'verbose_name_plural': 'Сетевые пути',
                'ordering': ['src_device__name', 'dst_device__name'],
            },
        ),
        migrations.CreateModel(
            name='NetworkOutage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('started_at', models.DateTimeField()),
                ('ended_at', models.DateTimeField(blank=True, null=True)),
                ('duration_sec', models.BigIntegerField(blank=True, null=True)),
                ('fail_count', models.PositiveIntegerField(default=0)),
                ('recover_count', models.PositiveIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('last_probe_at', models.DateTimeField(blank=True, null=True)),
                ('last_error', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('path', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='outages', to='inventory_api.networkpath')),
            ],
            options={
                'verbose_name': 'Сетевое пропадание',
                'verbose_name_plural': 'Сетевые пропадания',
                'ordering': ['-started_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='networkpath',
            constraint=models.UniqueConstraint(fields=('src_device', 'dst_device'), name='uniq_network_path_src_dst'),
        ),
        migrations.AddConstraint(
            model_name='networkpath',
            constraint=models.CheckConstraint(condition=~models.Q(src_device=models.F('dst_device')), name='chk_network_path_src_ne_dst'),
        ),
        migrations.AddIndex(
            model_name='networkpath',
            index=models.Index(fields=['enabled', 'last_state'], name='inventory_a_enabled_8bfdd2_idx'),
        ),
        migrations.AddIndex(
            model_name='networkpath',
            index=models.Index(fields=['src_device', 'dst_device'], name='inventory_a_src_dev_599453_idx'),
        ),
        migrations.AddIndex(
            model_name='networkoutage',
            index=models.Index(fields=['path', 'is_active', '-started_at'], name='inventory_a_path_id_cc93da_idx'),
        ),
        migrations.AddIndex(
            model_name='networkoutage',
            index=models.Index(fields=['is_active', '-started_at'], name='inventory_a_is_acti_3f2d29_idx'),
        ),
    ]
