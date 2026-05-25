from django.contrib.auth.models import Group, User
from django.urls import reverse
from rest_framework.test import APITestCase


class SystemHealthApiTests(APITestCase):
    def setUp(self):
        self.admin_group, _ = Group.objects.get_or_create(name="Admins")
        self.admin = User.objects.create_user(username="admin", password="pass", is_staff=True)
        self.admin.groups.add(self.admin_group)
        self.user = User.objects.create_user(username="plain", password="pass")

    def test_admin_can_read_summary(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(f"{reverse('system-health-summary')}?lstm=0")
        self.assertEqual(response.status_code, 200)
        self.assertIn(response.data["status"], {"ok", "warning", "critical"})
        self.assertIn("resources", response.data)
        self.assertIn("queues", response.data)
        self.assertIn("counts", response.data)

    def test_non_admin_cannot_read_summary(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(f"{reverse('system-health-summary')}?lstm=0")
        self.assertEqual(response.status_code, 403)
