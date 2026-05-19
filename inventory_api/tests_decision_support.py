from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APITestCase

from inventory_api.forecasting.decision_support_service import (
    bootstrap_decision_defaults,
    run_decision_recommendation,
)
from inventory_api.models import (
    DecisionAction,
    DecisionCriterion,
    DecisionPolicy,
    DecisionPolicyLoss,
    DecisionRun,
    Device,
    DeviceType,
)


def _mock_risk_payload(horizon: str = '24h', metrics: list[dict] | None = None):
    if metrics is None:
        metrics = [
            {
                'metric_code': 'mem_usage_percent',
                'risk': 0.42,
                'contribution': 0.61,
                'method': 'threshold',
                'risk_level': 'medium',
            },
            {
                'metric_code': 'cpu_load_total',
                'risk': 0.19,
                'contribution': 0.19,
                'method': 'threshold',
                'risk_level': 'low',
            },
        ]
    return {
        'computed_at': '2026-03-15T00:00:00Z',
        'device': {'id': 1, 'serial_number': 'HOST-DEC-001'},
        'horizons': [
            {
                'horizon': horizon,
                'overall_risk': 0.42,
                'metric_aggregate_risk': 0.31,
                'markov_projected_p_s2': 0.53,
                'current_state': {'s0': 0.30, 's1': 0.30, 's2': 0.40},
                'projected_state': {'s0': 0.20, 's1': 0.27, 's2': 0.53},
                'model_kind_used': 'ensemble',
                'run_id_used': 123,
                'metrics': metrics,
            }
        ],
    }


class DecisionSupportServiceTests(TestCase):
    def setUp(self):
        self.device_type = DeviceType.objects.create(name='Сервер')
        self.device = Device.objects.create(
            name='Decision Host',
            serial_number='HOST-DEC-001',
            device_type=self.device_type,
            status='active',
        )

    def test_bootstrap_defaults_creates_policies_actions_and_losses(self):
        policies = bootstrap_decision_defaults()
        self.assertEqual(len(policies), 3)
        self.assertGreaterEqual(DecisionAction.objects.count(), 4)
        self.assertGreaterEqual(DecisionCriterion.objects.count(), 4)

        for horizon in ('24h', '7d', '30d'):
            policy = DecisionPolicy.objects.filter(horizon=horizon, scope='global', is_active=True).first()
            self.assertIsNotNone(policy)
            self.assertGreater(DecisionPolicyLoss.objects.filter(policy=policy).count(), 0)

    @patch('inventory_api.forecasting.decision_support_service.evaluate_risk_assessment')
    def test_run_decision_recommendation_creates_run_with_scores(self, evaluate_risk_assessment_mock):
        evaluate_risk_assessment_mock.return_value = _mock_risk_payload('24h')
        bootstrap_decision_defaults()

        run = run_decision_recommendation(
            device_id=self.device.id,
            horizon='24h',
            mode='advanced',
            bayes_weight=0.6,
            ahp_weight=0.4,
            overall_weight_markov=0.7,
        )

        self.assertIsInstance(run, DecisionRun)
        self.assertEqual(run.status, 'success')
        self.assertIsNotNone(run.recommended_action)
        self.assertGreater(run.scores.count(), 0)
        self.assertEqual(run.mode, 'advanced')
        self.assertAlmostEqual(float(run.risk_snapshot.get('p_s2', 0.0)), 0.53, places=4)
        self.assertEqual(run.risk_snapshot.get('state_probability_source'), 'projected_state')
        self.assertTrue(hasattr(run, 'ahp'))

    @patch('inventory_api.forecasting.decision_support_service.evaluate_risk_assessment')
    def test_recommendation_filters_actions_by_active_risk_metrics(self, evaluate_risk_assessment_mock):
        evaluate_risk_assessment_mock.return_value = _mock_risk_payload(
            '24h',
            metrics=[
                {'metric_code': 'mem_usage_percent', 'risk': 0.55, 'contribution': 0.72},
                {'metric_code': 'storcli_drive_temperature', 'risk': 0.03, 'contribution': 0.01},
            ],
        )
        bootstrap_decision_defaults()

        DecisionAction.objects.filter(code='replace_ssd_now').update(
            constraints_json={'metric_codes': ['storcli_drive_temperature']}
        )
        DecisionAction.objects.filter(code='live_migration').update(
            constraints_json={'metric_codes': ['mem_usage_percent']}
        )
        DecisionAction.objects.filter(code='defer_to_night').update(
            constraints_json={'metric_codes': ['mem_usage_percent']}
        )
        DecisionAction.objects.filter(code='no_action').update(
            constraints_json={'metric_codes': ['mem_usage_percent']}
        )

        run = run_decision_recommendation(
            device_id=self.device.id,
            horizon='24h',
            mode='bayes',
        )
        self.assertIsNotNone(run.recommended_action)

        score_map = {row.action.code: row for row in run.scores.all()}
        self.assertIn('replace_ssd_now', score_map)
        self.assertFalse(score_map['replace_ssd_now'].explanation.get('allowed'))
        self.assertTrue(score_map['replace_ssd_now'].explanation.get('excluded_reasons'))
        self.assertTrue(score_map['live_migration'].explanation.get('allowed'))

    @patch('inventory_api.forecasting.decision_support_service.evaluate_risk_assessment')
    def test_no_action_is_disabled_under_critical_risk(self, evaluate_risk_assessment_mock):
        payload = _mock_risk_payload('30d')
        payload['horizons'][0]['overall_risk'] = 0.91
        payload['horizons'][0]['markov_projected_p_s2'] = 0.93
        payload['horizons'][0]['projected_state'] = {'s0': 0.03, 's1': 0.08, 's2': 0.89}
        evaluate_risk_assessment_mock.return_value = payload
        bootstrap_decision_defaults()

        run = run_decision_recommendation(
            device_id=self.device.id,
            horizon='30d',
            mode='bayes',
        )
        score_map = {row.action.code: row for row in run.scores.all()}
        self.assertIn('no_action', score_map)
        no_action = score_map['no_action']
        self.assertFalse(no_action.explanation.get('allowed'))
        reasons = no_action.explanation.get('excluded_reasons') or []
        self.assertTrue(any('no_action отключено' in str(item) for item in reasons))


class DecisionSupportApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin_decision', password='pass123', is_staff=True)
        self.client.force_authenticate(user=self.admin)

        device_type = DeviceType.objects.create(name='Сервер')
        self.device = Device.objects.create(
            name='Decision API Host',
            serial_number='HOST-DEC-API-001',
            device_type=device_type,
            status='active',
        )

    @patch('inventory_api.forecasting.decision_support_service.evaluate_risk_assessment')
    def test_recommend_and_feedback_flow(self, evaluate_risk_assessment_mock):
        evaluate_risk_assessment_mock.return_value = _mock_risk_payload('30d')

        boot_res = self.client.post('/api/decision-policies/bootstrap_defaults/', {}, format='json')
        self.assertEqual(boot_res.status_code, 200)

        policies_res = self.client.get('/api/decision-policies/?horizon=30d&is_active=true')
        self.assertEqual(policies_res.status_code, 200)
        if isinstance(policies_res.data, list):
            policies_rows = policies_res.data
        else:
            policies_rows = policies_res.data.get('results', policies_res.data)
        self.assertGreater(len(policies_rows), 0)
        policy_id = policies_rows[0]['id']

        run_res = self.client.post(
            '/api/decision-runs/recommend_advanced/',
            {
                'device': self.device.id,
                'horizon': '30d',
                'policy_id': policy_id,
                'overall_weight_markov': 0.6,
                'bayes_weight': 0.5,
                'ahp_weight': 0.5,
            },
            format='json',
        )
        self.assertEqual(run_res.status_code, 200)
        run_id = run_res.data['id']
        self.assertIsNotNone(run_res.data.get('recommended_action'))

        feedback_res = self.client.post(
            f'/api/decision-runs/{run_id}/feedback/',
            {
                'actual_action': run_res.data.get('recommended_action'),
                'outcome_state': 's1',
                'outage_minutes': 15,
                'incident_cost': 12000,
                'notes': 'Проверка цикла обратной связи',
            },
            format='json',
        )
        self.assertEqual(feedback_res.status_code, 200)
        self.assertEqual(feedback_res.data.get('id'), run_id)
        self.assertEqual(feedback_res.data.get('feedback', {}).get('outcome_state'), 's1')
