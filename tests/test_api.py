from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["product"] == "RelayGrid"
    assert body["agents"] >= 5


def test_list_agents_hides_api_keys():
    response = client.get("/api/v1/agents")
    assert response.status_code == 200
    agents = response.json()
    names = {a["company_name"] for a in agents}
    assert {"MealRun", "PayPulse", "Northstar Bank", "VoltRide", "CartWave"} <= names
    assert all("api_key" not in a for a in agents)


def test_city_lights_does_not_notify_voltride():
    agents = {a["company_name"]: a for a in client.get("/api/v1/agents").json()}
    mealrun = agents["MealRun"]
    response = client.post(
        "/api/v1/posts",
        json={
            "author_agent_id": mealrun["id"],
            "title": "City Lights late-night delivery offer",
            "content": "5% off all MealRun deliveries. Wallet and card cashback partners welcome.",
            "tags": ["food delivery", "cashback"],
        },
    )
    assert response.status_code == 201
    routing = {row["company_name"]: row for row in response.json()["routing"]}
    assert routing["VoltRide"]["notified"] is False
    notified = {name for name, row in routing.items() if row["notified"]}
    assert "PayPulse" in notified
    assert "Northstar Bank" in notified


def test_register_duplicate_slug_conflicts():
    payload = {
        "company_name": "MealRun",
        "slug": "mealrun",
        "industry_category": "Food Delivery",
        "webhook_url": "http://127.0.0.1:8000/mock-agents/mealrun/webhook",
        "interest_manifesto": "Interested in payment partnerships and late-night food campaigns.",
    }
    response = client.post("/api/v1/agents/register", json=payload)
    assert response.status_code == 409
