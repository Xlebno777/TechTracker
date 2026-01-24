import secrets

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from rest_framework.authtoken.models import Token


class Command(BaseCommand):
    help = "Create or update a printer agent user with limited permissions."

    def add_arguments(self, parser):
        parser.add_argument('--username', default='printer_agent')
        parser.add_argument('--password', default='')

    def handle(self, *args, **options):
        username = options['username']
        password = options['password'] or secrets.token_urlsafe(16)

        group, _ = Group.objects.get_or_create(name='PrinterAgents')

        user, created = User.objects.get_or_create(username=username)
        if created:
            user.set_password(password)
            user.is_staff = False
            user.is_superuser = False
            user.save()
        else:
            if options['password']:
                user.set_password(password)
                user.save()

        user.groups.add(group)

        token, _ = Token.objects.get_or_create(user=user)

        self.stdout.write(self.style.SUCCESS(f"Printer agent user: {username}"))
        if created or options['password']:
            self.stdout.write(self.style.WARNING(f"Password: {password}"))
        self.stdout.write(self.style.SUCCESS(f"Token: {token.key}"))
