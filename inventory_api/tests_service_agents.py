from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from inventory_api.models import AgentCommand, Device, DeviceType, ServiceAgent


class ServiceAgentCommandManagementTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="agent-admin",
            password="pass",
            is_staff=True,
        )
        self.client.force_authenticate(self.admin)
        device_type = DeviceType.objects.create(name="Server")
        self.device = Device.objects.create(
            name="KRTB-DEMOHOST",
            serial_number="VirtualBox-123",
            device_type=device_type,
        )
        self.agent = ServiceAgent.objects.create(
            device=self.device,
            agent_version="0.2.15",
            status="online",
            last_update_status="pending",
        )

    def test_cancel_command_marks_update_cancelled_and_ignores_late_agent_result(self):
        command = AgentCommand.objects.create(
            agent=self.agent,
            command="update",
            status="running",
            payload={"target_version": "0.2.16"},
        )

        cancel_response = self.client.post(
            f"/api/agents/commands/{command.id}/cancel/",
            {"reason": "Остановка по запросу администратора."},
            format="json",
        )

        self.assertEqual(cancel_response.status_code, 200)
        command.refresh_from_db()
        self.agent.refresh_from_db()
        self.assertEqual(command.status, "cancelled")
        self.assertEqual(command.result_message, "Остановка по запросу администратора.")
        self.assertIsNotNone(command.finished_at)
        self.assertEqual(self.agent.last_update_status, "failed")
        self.assertEqual(self.agent.last_update_message, "Остановка по запросу администратора.")

        result_response = self.client.post(
            f"/api/agents/commands/{command.id}/result/",
            {
                "serial_number": self.device.serial_number,
                "status": "success",
                "result_message": "late success",
            },
            format="json",
        )

        self.assertEqual(result_response.status_code, 200)
        command.refresh_from_db()
        self.agent.refresh_from_db()
        self.assertEqual(command.status, "cancelled")
        self.assertEqual(command.result_message, "Остановка по запросу администратора.")
        self.assertEqual(self.agent.last_update_status, "failed")

    def test_delete_command_removes_selected_command(self):
        command = AgentCommand.objects.create(
            agent=self.agent,
            command="restart",
            status="pending",
        )

        response = self.client.delete(f"/api/agents/commands/{command.id}/")

        self.assertEqual(response.status_code, 204)
        self.assertFalse(AgentCommand.objects.filter(id=command.id).exists())
