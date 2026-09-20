"""Recommendations consume released aggregates and record revision-bound review."""

from .fixtures import cover_all, end, headers, setup, signal


def test_recommendations_and_stale_review():
    client, session, base = setup()
    cover_all(client, base)
    signal(client, session, base)
    signal(client, session, base, user="s2", event_id="e2")
    end(client, base)
    response = client.post(
        base + "/professor-recommendations", headers=headers("prof", "professor")
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["recommendations"]) == 1 and body["provider_mode"] == "mock"
    review = {
        "report_revision": body["report_revision"],
        "recommendation_index": 0,
        "status": "dismissed",
    }
    assert (
        client.put(
            base + "/professor-recommendations/reviews",
            headers=headers("prof", "professor"),
            json=review,
        ).status_code
        == 200
    )
    refreshed = client.post(
        base + "/professor-recommendations", headers=headers("prof", "professor")
    ).json()
    assert refreshed["reviews"][0]["status"] == "dismissed"
    client.app.state.store.participants[session]["s5"].is_opted_in = False
    assert (
        client.put(
            base + "/professor-recommendations/reviews",
            headers=headers("prof", "professor"),
            json=review,
        ).status_code
        == 409
    )
    assert (
        client.post(
            base + "/professor-recommendations", headers=headers("prof", "professor")
        ).json()["recommendations"]
        == []
    )


def test_student_cannot_generate_teaching_recommendations():
    client, _session, base = setup()
    end(client, base)
    assert (
        client.post(base + "/professor-recommendations", headers=headers()).status_code
        == 403
    )
