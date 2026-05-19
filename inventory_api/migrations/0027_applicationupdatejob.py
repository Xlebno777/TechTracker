from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inventory_api', '0026_stateinferenceprofile_orchestrator_controls'),
    ]

    operations = [
        migrations.CreateModel(
            name='ApplicationUpdateJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('queued', 'Queued'), ('running', 'Running'), ('completed', 'Completed'), ('failed', 'Failed'), ('skipped', 'Skipped')], default='queued', max_length=20)),
                ('current_version', models.CharField(blank=True, max_length=50)),
                ('target_version', models.CharField(blank=True, max_length=50)),
                ('release_channel', models.CharField(default='single', max_length=50)),
                ('manifest_url', models.TextField(blank=True)),
                ('git_ref', models.CharField(blank=True, max_length=200)),
                ('release_notes', models.JSONField(blank=True, default=list)),
                ('parameters', models.JSONField(blank=True, default=dict)),
                ('log', models.TextField(blank=True)),
                ('error', models.TextField(blank=True)),
                ('pid', models.IntegerField(blank=True, null=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='application_update_jobs_created', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Задание обновления приложения',
                'verbose_name_plural': 'Задания обновления приложения',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='applicationupdatejob',
            index=models.Index(fields=['status', '-created_at'], name='inventory_a_status_4c75a2_idx'),
        ),
        migrations.AddIndex(
            model_name='applicationupdatejob',
            index=models.Index(fields=['target_version', '-created_at'], name='inventory_a_target__c60357_idx'),
        ),
    ]
