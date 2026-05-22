from django.contrib.auth.models import Group, User
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase


class UserManagementApiTests(APITestCase):
    def setUp(self):
        self.admin_group, _ = Group.objects.get_or_create(name="Admins")
        self.admin = User.objects.create_user(username="admin", password="pass", is_staff=True)
        self.admin.groups.add(self.admin_group)
        self.user = User.objects.create_user(username="plain", password="pass")

    def test_non_admin_cannot_list_managed_users(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse("managed-users-list"))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_create_user_group_and_token(self):
        self.client.force_authenticate(self.admin)

        group_response = self.client.post(reverse("managed-groups-list"), {"name": "MetricsAgents", "permissions": []}, format="json")
        self.assertEqual(group_response.status_code, 201)
        group_id = group_response.data["id"]

        user_response = self.client.post(
            reverse("managed-users-list"),
            {
                "username": "metrics_agent_01",
                "email": "metrics@example.local",
                "is_active": True,
                "is_staff": False,
                "is_superuser": False,
                "group_ids": [group_id],
            },
            format="json",
        )
        self.assertEqual(user_response.status_code, 201)
        user_id = user_response.data["id"]
        self.assertEqual(user_response.data["groups"][0]["name"], "MetricsAgents")

        token_response = self.client.post(reverse("managed-users-generate-token", args=[user_id]), {}, format="json")
        self.assertEqual(token_response.status_code, 200)
        self.assertTrue(token_response.data["token"])
        self.assertTrue(Token.objects.filter(user_id=user_id).exists())

        clear_response = self.client.post(reverse("managed-users-clear-token", args=[user_id]), {}, format="json")
        self.assertEqual(clear_response.status_code, 200)
        self.assertFalse(Token.objects.filter(user_id=user_id).exists())

    def test_admin_can_bootstrap_default_groups(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(reverse("managed-groups-bootstrap-defaults"), {}, format="json")
        self.assertEqual(response.status_code, 200)
        for name in ["Admins", "Users", "Agent", "PrinterAgents", "MetricsAgents", "VMAgents"]:
            self.assertTrue(Group.objects.filter(name=name).exists())
