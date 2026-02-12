from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory_api', '0015_networkpath_networkoutage'),
    ]

    operations = [
        migrations.CreateModel(
            name='NetworkAlertRule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=100, unique=True)),
                ('name', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True)),
                ('metric_code', models.CharField(max_length=100)),
                ('window', models.CharField(default='24h', max_length=20)),
                ('comparison', models.CharField(choices=[('gt', '>'), ('gte', '>='), ('lt', '<'), ('lte', '<='), ('eq', '='), ('ne', '!=')], default='gt', max_length=10)),
                ('threshold_value', models.FloatField()),
                ('severity', models.CharField(choices=[('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')], default='medium', max_length=20)),
                ('enabled', models.BooleanField(default=True)),
                ('order', models.PositiveIntegerField(default=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Правило сетевой тревоги',
                'verbose_name_plural': 'Правила сетевых тревог',
                'ordering': ['order', 'name'],
            },
        ),
        migrations.AddIndex(
            model_name='networkalertrule',
            index=models.Index(fields=['enabled', 'order'], name='inventory_a_enabled_38fe27_idx'),
        ),
        migrations.AddIndex(
            model_name='networkalertrule',
            index=models.Index(fields=['metric_code', 'window'], name='inventory_a_metric__c36751_idx'),
        ),
    ]
