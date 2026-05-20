import os

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create or update a TechTracker administrator user."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--email", default="")
        parser.add_argument("--password", default="")
        parser.add_argument("--password-env", default="")
        parser.add_argument("--no-superuser", action="store_true")

    def handle(self, *args, **options):
        username = str(options["username"] or "").strip()
        email = str(options.get("email") or "").strip()
        password = str(options.get("password") or "")
        password_env = str(options.get("password_env") or "").strip()

        if password_env:
            password = os.environ.get(password_env, "")

        if not username:
            raise CommandError("--username is required")
        if not password:
            raise CommandError("Password is required. Use --password or --password-env.")

        admin_group, _ = Group.objects.get_or_create(name="Admins")
        user, created = User.objects.get_or_create(username=username, defaults={"email": email})
        if email and user.email != email:
            user.email = email

        user.is_staff = True
        user.is_superuser = not bool(options.get("no_superuser"))
        user.set_password(password)
        user.save()
        user.groups.add(admin_group)

        state = "created" if created else "updated"
        self.stdout.write(self.style.SUCCESS(f"Admin user {state}: {username}"))
