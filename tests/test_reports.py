from sc2_replay_reviewer.config import AppConfig
from sc2_replay_reviewer.reports import render_evidence, render_review


def _bundle():
    extraction = {
        "schema_version": "1.0",
        "replay_hash": "abc123",
        "parser": {"version": "test-parser"},
        "metadata": {
            "game_speed": "Faster",
            "duration_loops": 10000,
            "map": "Test Map",
            "game_mode": "Amm",
            "teams": "1v1",
        },
        "players": [{"player_id": 1, "name": "ReviewedPlayer", "race": "Zerg", "result": "Win"}],
        "warnings": [],
    }
    derivation = {
        "player_snapshots": [
            {
                "player_id": 1,
                "game_loop": 9000,
                "workers_active_count": 45,
                "food_used": 100,
                "food_made": 120,
                "minerals_current": 1200,
                "vespene_current": 600,
                "minerals_collection_rate": 1500,
                "vespene_collection_rate": 600,
                "minerals_used_active_forces": 2000,
                "vespene_used_active_forces": 1000,
                "evidence_id": "tracker:1",
            }
        ],
        "economy": {
            "candidate_supply_blocks": [{"player_id": 1, "start_loop": 8000, "supply_used": 120, "supply_available": 120, "evidence": ["tracker:2"]}],
            "candidate_resource_floats": [{"player_id": 1, "game_loop": 9000, "minerals": 1200, "vespene": 600, "evidence": ["tracker:1"]}],
            "float_episodes": [{
                "player_id": 1,
                "start_loop": 8000,
                "end_loop": 10000,
                "duration_loops": 2000,
                "peak_loop": 9000,
                "peak_minerals": 1200,
                "peak_gas": 600,
                "worker_count_at_start": 30,
                "worker_count_at_peak": 45,
                "base_count_at_peak": 3,
                "supply_at_peak": {"used": 120, "available": 120},
                "available_production_capacity": 3,
                "available_larva": 2,
                "constraints": ["supply_blocked"],
                "primary_constraint": "supply_blocked",
                "actively_fighting": False,
                "bank_spent_after_active_fighting": False,
                "completed_upgrades_at_peak": [],
                "evidence": ["tracker:1"],
                "meaningful": True,
                "purchasing_power": {
                    "Roach": {"resource_bound": 16, "immediate_upper_bound": 0, "supply_bound": 0, "larva_bound": 2, "tech_available": True},
                    "Zergling": {"resource_bound": 48, "immediate_upper_bound": 0, "supply_bound": 0, "larva_bound": 2, "tech_available": True},
                },
            }],
            "resource_collection_disruptions": [{"player_id": 2, "start_loop": 4000, "end_loop": 4200, "minerals_collection_rate_before": 783, "minerals_collection_rate_after": 195, "evidence": ["tracker:3", "tracker:4"]}],
        },
        "losses": {"worker_deaths": [], "worker_loss_summary_by_player": {}},
        "timing": {"completed_structures": [], "expansions": [], "upgrades": []},
        "composition_snapshots": [],
    }
    engagement = {
        "engagement_id": "engagement:15",
        "start_loop": 7000,
        "end_loop": 8000,
        "participants": [1, 2],
        "losses_by_player": {"1": {"units": 16}, "2": {"units": 52}},
        "kills_by_player": {"1": {"Immortal": 4, "Probe": 35, "Pylon": 3}},
        "loss_types_by_player": {"1": {"Roach": 16}},
        "centroid": [42, 39],
        "death_count": 68,
        "reinforcement_waves": [],
        "evidence": ["tracker:5"],
    }
    diagnosis = {
        "decisive_candidate": {"engagement_id": None, "game_loop": None},
        "turning_point_candidate": {"engagement_id": "engagement:15", "game_loop": 7000, "assessment": {"label": "even_or_favorable"}},
        "facts": [],
        "inferences": [],
    }
    timeline = [{"game_loop": 7000, "real_time": "5:12", "event_kind": "engagement", "player": "ReviewedPlayer", "factual_statement": "A clustered engagement was detected.", "evidence_refs": "tracker:5"}]
    return extraction, derivation, [engagement], diagnosis, timeline


def test_review_is_compressed_and_spending_first():
    extraction, derivation, engagements, diagnosis, _ = _bundle()
    review = render_review(extraction, derivation, engagements, diagnosis, 1, AppConfig())
    assert 200 <= len(review.split()) <= 400
    assert review.count("\n## ") == 5
    assert "Timestamps use real elapsed time." in review
    assert "game time" not in review.lower()
    assert "Macro benchmark/reality:" in review
    assert "## Spending verdict" in review
    assert "## Float timeline" in review
    assert "## Next-game trigger" in review


def test_evidence_report_keeps_timeline_and_audit_sections():
    extraction, derivation, engagements, diagnosis, timeline = _bundle()
    evidence = render_evidence(extraction, derivation, engagements, diagnosis, timeline, 1, AppConfig())
    assert "## 4. Timeline of meaningful events" in evidence
    assert "A clustered engagement was detected." in evidence
    assert "## 14. Evidence appendix" in evidence
    assert "Evidence methodology and limitations" in evidence
    assert "tracker:5" in evidence
    assert "Meaningful resource-float episodes" in evidence
