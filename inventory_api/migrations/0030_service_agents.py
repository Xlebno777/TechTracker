# Generated manually for service-agent management.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory_api', '0029_perf_indexes_and_api_caps'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ServiceAgent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(default='TechTracker Agent', max_length=200)),
                ('agent_uid', models.CharField(blank=True, max_length=100, null=True, unique=True)),
                ('installation_type', models.CharField(choices=[('service', 'Windows Service'), ('legacy', 'Legacy')], default='service', max_length=20)),
                ('service_name', models.CharField(blank=True, default='TechTrackerAgent', max_length=100)),
                ('service_status', models.CharField(blank=True, max_length=50)),
                ('agent_version', models.CharField(blank=True, max_length=50)),
                ('host_name', models.CharField(blank=True, max_length=200)),
                ('os_name', models.CharField(blank=True, max_length=200)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('status', models.CharField(choices=[('online', 'Online'), ('error', 'Error'), ('offline', 'Offline'), ('unknown', 'Unknown')], default='unknown', max_length=20)),
                ('last_status_message', models.TextField(blank=True)),
                ('last_seen_at', models.DateTimeField(blank=True, null=True)),
                ('metrics_config', models.JSONField(blank=True, default=dict)),
                ('supported_metrics', models.JSONField(blank=True, default=list)),
                ('desired_version', models.CharField(blank=True, max_length=50)),
                ('last_update_status', models.CharField(choices=[('idle', 'Idle'), ('pending', 'Pending'), ('running', 'Running'), ('success', 'Success'), ('failed', 'Failed')], default='idle', max_length=20)),
                ('last_update_started_at', models.DateTimeField(blank=True, null=True)),
                ('last_update_completed_at', models.DateTimeField(blank=True, null=True)),
                ('last_update_message', models.TextField(blank=True)),
                ('installed_at', models.DateTimeField(auto_now_add=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('device', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='service_agent', to='inventory_api.device')),
            ],
            options={
                'verbose_name': 'Сервисный агент',
                'verbose_name_plural': 'Сервисные агенты',
                'ordering': ['-last_seen_at', 'device__name'],
            },
        ),
        migrations.CreateModel(
            name='AgentCommand',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('command', models.CharField(choices=[('restart', 'Restart'), ('update', 'Update'), ('set_metrics', 'Set metrics')], max_length=30)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('acknowledged', 'Acknowledged'), ('running', 'Running'), ('success', 'Success'), ('failed', 'Failed'), ('cancelled', 'Cancelled')], default='pending', max_length=20)),
                ('payload', models.JSONField(blank=True, default=dict)),
                ('result_message', models.TextField(blank=True)),
                ('acknowledged_at', models.DateTimeField(blank=True, null=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('agent', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='commands', to='inventory_api.serviceagent')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='agent_commands_created', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Команда агента',
                'verbose_name_plural': 'Команды агентов',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='serviceagent',
            index=models.Index(fields=['status', '-last_seen_at'], name='inventory_a_status__b7f096_idx'),
        ),
        migrations.AddIndex(
            model_name='serviceagent',
            index=models.Index(fields=['service_name'], name='inventory_a_service_e65bad_idx'),
        ),
        migrations.AddIndex(
            model_name='serviceagent',
            index=models.Index(fields=['agent_version'], name='inventory_a_agent_v_7cf576_idx'),
        ),
        migrations.AddIndex(
            model_name='agentcommand',
            index=models.Index(fields=['agent', 'status', 'created_at'], name='inventory_a_agent_i_850a8f_idx'),
        ),
        migrations.AddIndex(
            model_name='agentcommand',
            index=models.Index(fields=['command', 'status', '-created_at'], name='inventory_a_command_756971_idx'),
        ),
    ]
