"""Locust load test for {ServiceName} inference API.

Simulates concurrent prediction requests to measure:
- P50, P95, P99 latency
- Requests per second (RPS)
- Error rate under load
- Batch prediction throughput

How to run:
    # Start with web UI:
    locust -f tests/load_test.py --host=http://localhost:8000

    # Headless mode (CI/CD):
    locust -f tests/load_test.py --host=http://localhost:8000 \
        --headless -u 100 -r 10 --run-time 60s \
        --csv=reports/load_test

    # Against K8s service:
    locust -f tests/load_test.py --host=http://{service}.ml-services.svc.cluster.local:8000 \
        --headless -u 100 -r 10 --run-time 120s

Acceptance criteria (from new-service skill):
    - Error rate < 1% under 100 concurrent users
    - P95 latency within SLA (default: 100ms for single, 1s for batch)

TODO: Replace SAMPLE_PAYLOAD with your actual feature schema.
TODO: Adjust user count and spawn rate for your expected traffic.
"""

from locust import HttpUser, between, task

# ---------------------------------------------------------------------------
# Configuration — customize per service
# ---------------------------------------------------------------------------
# TODO: Replace with actual features matching your Pydantic schema
SAMPLE_PAYLOAD = {
    "feature_1": 42.0,
    "feature_2": 600,
    "feature_3": 1,
    "feature_4": 50000.0,
}

BATCH_SIZE = 10
BATCH_PAYLOAD = {
    "instances": [SAMPLE_PAYLOAD] * BATCH_SIZE,
}


class MLServiceUser(HttpUser):
    """Simulates a user making prediction requests.

    wait_time: Random delay between requests (1-3 seconds)
    to simulate realistic traffic patterns.
    """

    wait_time = between(1, 3)

    @task(5)
    def predict_single(self) -> None:
        """Single prediction — most common request type (weight=5)."""
        self.client.post(
            "/predict",
            json=SAMPLE_PAYLOAD,
            name="/predict [single]",
        )

    @task(2)
    def predict_with_explanation(self) -> None:
        """Single prediction with SHAP explanation (weight=2).

        Expected to be slower — SHAP adds computation overhead.
        """
        self.client.post(
            "/predict?explain=true",
            json=SAMPLE_PAYLOAD,
            name="/predict [with SHAP]",
        )

    @task(1)
    def predict_batch(self) -> None:
        """Batch prediction (weight=1)."""
        self.client.post(
            "/predict_batch",
            json=BATCH_PAYLOAD,
            name=f"/predict_batch [{BATCH_SIZE}]",
        )

    @task(1)
    def health_check(self) -> None:
        """Health endpoint — lightweight, verifies service is up."""
        self.client.get("/health", name="/health")

    @task(1)
    def metrics(self) -> None:
        """Prometheus metrics endpoint."""
        self.client.get("/metrics", name="/metrics")
