from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventory_api', '0009_computedmetric'),
    ]

    operations = [
        migrations.CreateModel(
            name='AgentStatus',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('ok', 'OK'), ('error', 'Error')], default='ok', max_length=20)),
                ('message', models.TextField(blank=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='agent_statuses', to='inventory_api.device')),
            ],
            options={
                'verbose_name': 'Статус агента',
                'verbose_name_plural': 'Статусы агентов',
                'ordering': ['-updated_at'],
            },
        ),
        migrations.AddIndex(
            model_name='agentstatus',
            index=models.Index(fields=['device', 'status', '-updated_at'], name='inventory_a_device__0d3b2a_idx'),
        ),
        migrations.AddIndex(
            model_name='agentstatus',
            index=models.Index(fields=['status', '-updated_at'], name='inventory_a_status__a1e6d7_idx'),
        ),
    ]

