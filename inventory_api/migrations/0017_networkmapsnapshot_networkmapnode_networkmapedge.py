from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('inventory_api', '0016_networkalertrule'),
    ]

    operations = [
        migrations.CreateModel(
            name='NetworkMapSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('generated_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('source_window_hours', models.PositiveIntegerField(default=24)),
                ('node_count', models.PositiveIntegerField(default=0)),
                ('edge_count', models.PositiveIntegerField(default=0)),
                ('build_duration_ms', models.PositiveIntegerField(blank=True, null=True)),
                ('status', models.CharField(choices=[('ok', 'OK'), ('error', 'Error')], default='ok', max_length=20)),
                ('error', models.TextField(blank=True)),
                ('is_current', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Снимок сетевой карты',
                'verbose_name_plural': 'Снимки сетевой карты',
                'ordering': ['-generated_at', '-id'],
            },
        ),
        migrations.CreateModel(
            name='NetworkMapNode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('device_name', models.CharField(max_length=200)),
                ('serial_number', models.CharField(blank=True, max_length=100)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('device_type_name', models.CharField(blank=True, max_length=100)),
                ('status', models.CharField(blank=True, max_length=20)),
                ('last_seen', models.DateTimeField(blank=True, null=True)),
                ('device', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='network_map_nodes', to='inventory_api.device')),
                ('snapshot', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='nodes', to='inventory_api.networkmapsnapshot')),
            ],
            options={
                'verbose_name': 'Узел сетевой карты',
                'verbose_name_plural': 'Узлы сетевой карты',
                'ordering': ['device_name', 'id'],
            },
        ),
        migrations.CreateModel(
            name='NetworkMapEdge',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('src_name', models.CharField(max_length=200)),
                ('dst_name', models.CharField(max_length=200)),
                ('dst_ip', models.GenericIPAddressField(blank=True, null=True)),
                ('enabled', models.BooleanField(default=True)),
                ('state', models.CharField(choices=[('unknown', 'Unknown'), ('up', 'Up'), ('down', 'Down'), ('none', 'None')], default='unknown', max_length=20)),
                ('latency_ms', models.FloatField(blank=True, null=True)),
                ('packet_loss_pct', models.FloatField(blank=True, null=True)),
                ('confidence_pct', models.FloatField(blank=True, null=True)),
                ('outage_count_24h', models.PositiveIntegerField(default=0)),
                ('has_active_outage', models.BooleanField(default=False)),
                ('last_checked_at', models.DateTimeField(blank=True, null=True)),
                ('dst_device', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='network_map_edges_dst', to='inventory_api.device')),
                ('path', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='network_map_edges', to='inventory_api.networkpath')),
                ('snapshot', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='edges', to='inventory_api.networkmapsnapshot')),
                ('src_device', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='network_map_edges_src', to='inventory_api.device')),
            ],
            options={
                'verbose_name': 'Ребро сетевой карты',
                'verbose_name_plural': 'Ребра сетевой карты',
                'ordering': ['src_name', 'dst_name', 'id'],
            },
        ),
        migrations.AddIndex(
            model_name='networkmapsnapshot',
            index=models.Index(fields=['is_current', '-generated_at'], name='inv_map_snap_cur_5e0a2d_idx'),
        ),
        migrations.AddIndex(
            model_name='networkmapsnapshot',
            index=models.Index(fields=['status', '-generated_at'], name='inv_map_snap_st_1a9f5f_idx'),
        ),
        migrations.AddIndex(
            model_name='networkmapnode',
            index=models.Index(fields=['snapshot', 'device_name'], name='inv_map_node_sn_43af3e_idx'),
        ),
        migrations.AddIndex(
            model_name='networkmapnode',
            index=models.Index(fields=['snapshot', 'ip_address'], name='inv_map_node_ip_29d2bc_idx'),
        ),
        migrations.AddIndex(
            model_name='networkmapedge',
            index=models.Index(fields=['snapshot', 'state'], name='inv_map_edge_ss_22024b_idx'),
        ),
        migrations.AddIndex(
            model_name='networkmapedge',
            index=models.Index(fields=['snapshot', 'src_device', 'dst_device'], name='inv_map_edge_sd_2b76e4_idx'),
        ),
    ]
