from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase


class EnsureAdminUserCommandTests(TestCase):
    def test_creates_admin_user_and_group(self):
        call_command(
            "ensure_admin_user",
            username="installer_admin",
            email="admin@example.local",
            password="strong-pass-123",
        )

        user = User.objects.get(username="installer_admin")
        self.assertEqual(user.email, "admin@example.local")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password("strong-pass-123"))
        self.assertTrue(Group.objects.filter(name="Admins", user=user).exists())

    def test_updates_existing_admin_password(self):
        User.objects.create_user(username="installer_admin", password="old")
        call_command(
            "ensure_admin_user",
            username="installer_admin",
            email="new@example.local",
            password="new-pass-123",
        )

        user = User.objects.get(username="installer_admin")
        self.assertEqual(user.email, "new@example.local")
        self.assertTrue(user.check_password("new-pass-123"))
