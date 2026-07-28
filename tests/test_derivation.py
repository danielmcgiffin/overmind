from sc2_replay_reviewer.derive import derive_facts
from sc2_replay_reviewer.engagements import detect_engagements
from sc2_replay_reviewer.review import _engagement_assessment


def _event(evidence_id, event_type, game_loop, **kwargs):
    return {
        "evidence_id": evidence_id,
        "event_type": event_type,
        "game_loop": game_loop,
        **kwargs,
    }


def _extraction():
    return {
        "schema_version": "1.0",
        "players": [
            {"player_id": 1, "name": "Danny", "race": "Zerg", "team_id": 1},
            {"player_id": 2, "name": "Opponent", "race": "Terran", "team_id": 2},
        ],
        "tracker_events": [
            _event("s1", "PlayerStats", 160, player_id=1, stats={"workers_active_count": 20, "food_used": 40, "food_made": 44, "minerals_current": 100, "vespene_current": 50, "minerals_used_active_forces": 400, "vespene_used_active_forces": 100}),
            _event("s2", "PlayerStats", 160, player_id=2, stats={"workers_active_count": 22, "food_used": 42, "food_made": 50, "minerals_current": 100, "vespene_current": 50, "minerals_used_active_forces": 500, "vespene_used_active_forces": 100}),
            _event("s3", "PlayerStats", 320, player_id=1, stats={"workers_active_count": 17, "food_used": 44, "food_made": 50, "minerals_current": 900, "vespene_current": 50, "minerals_used_active_forces": 100, "vespene_used_active_forces": 50}),
            _event("s4", "PlayerStats", 320, player_id=2, stats={"workers_active_count": 24, "food_used": 48, "food_made": 60, "minerals_current": 100, "vespene_current": 50, "minerals_used_active_forces": 600, "vespene_used_active_forces": 100}),
            _event("b1", "UnitBorn", 100, unit_tag=1 << 18, unit_type="Marine", owner_id=2, control_id=2, position=[10, 10]),
            _event("b2", "UnitBorn", 100, unit_tag=2 << 18, unit_type="Zergling", owner_id=1, control_id=1, position=[11, 10]),
            _event("b3", "UnitBorn", 100, unit_tag=3 << 18, unit_type="Roach", owner_id=1, control_id=1, position=[12, 11]),
            _event("b4", "UnitBorn", 100, unit_tag=4 << 18, unit_type="Marine", owner_id=2, control_id=2, position=[13, 10]),
            _event("bl", "UnitBorn", 100, unit_tag=7 << 18, unit_type="Larva", owner_id=1, control_id=1, position=[12, 10]),
            _event("b5", "UnitBorn", 260, unit_tag=5 << 18, unit_type="Zergling", owner_id=1, control_id=1, position=[12, 11]),
            _event("b6", "UnitBorn", 260, unit_tag=6 << 18, unit_type="Zergling", owner_id=1, control_id=1, position=[13, 11]),
            _event("d1", "UnitDied", 240, unit_tag=1 << 18, position=[10, 10], killer_player_id=1),
            _event("d2", "UnitDied", 240, unit_tag=2 << 18, position=[11, 10], killer_player_id=2),
            _event("d3", "UnitDied", 248, unit_tag=3 << 18, position=[12, 11], killer_player_id=2),
            _event("d4", "UnitDied", 248, unit_tag=4 << 18, position=[13, 10], killer_player_id=1),
            _event("dl", "UnitDied", 248, unit_tag=7 << 18, position=[12, 10], killer_player_id=2),
            _event("d5", "UnitDied", 900, unit_tag=5 << 18, position=[100, 100], killer_player_id=2),
        ],
        "game_events": [],
        "message_events": [],
        "attributes": {},
    }


def test_worker_differential_and_loss_aggregation():
    facts = derive_facts(_extraction())
    diffs = facts["worker_differentials"]
    assert diffs[0]["worker_diff"] == -2
    assert facts["losses"]["unit_losses_by_player"]["1"]["Zergling"] == 2
    assert len(facts["losses"]["worker_deaths"]) == 0


def test_army_value_uses_player_stats_when_available():
    facts = derive_facts(_extraction())
    composition = [item for item in facts["composition_snapshots"] if item["player_id"] == 1]
    assert composition[0]["army_value"] == 500
    assert composition[0]["army_value_source"] == "player_stats.active_forces"


def test_engagement_clustering_requires_space_and_time():
    facts = derive_facts(_extraction())
    engagements = detect_engagements(facts)
    assert len(engagements) == 1
    engagement = engagements[0]
    assert engagement["start_loop"] == 240
    assert engagement["death_count"] == 4
    assert engagement["reinforcement_waves"]
    assert engagement["reinforcement_waves"][0]["unit_count"] == 2


def test_small_force_structure_harassment_is_not_classified_as_a_lost_fight():
    engagement = {
        "losses_by_player": {
            "1": {"units": 6, "known_minerals": 150, "known_gas": 0, "army_units": 6},
            "2": {"units": 2, "known_minerals": 150, "known_gas": 0, "army_units": 0},
        },
        "loss_types_by_player": {"1": {"Zergling": 6}},
        "kills_by_player": {"1": {"Probe": 1, "Pylon": 1}},
    }
    assessment = _engagement_assessment(engagement, 1, [2])
    assert assessment["label"] == "favorable_harassment"


def test_zerg_drone_events_are_decomposed_against_worker_consuming_buildings():
    extraction = _extraction()
    extraction["tracker_events"].extend(
        [
            _event("drone-born", "UnitBorn", 500, unit_tag=8 << 18, unit_type="Drone", owner_id=1, control_id=1, position=[20, 20]),
            _event("building-init", "UnitInit", 500, unit_tag=9 << 18, unit_type="Hatchery", owner_id=1, control_id=1, position=[20, 20]),
            _event("drone-death", "UnitDied", 520, unit_tag=8 << 18, position=[20, 20]),
        ]
    )
    facts = derive_facts(extraction)
    summary = facts["losses"]["worker_loss_summary_by_player"]["1"]
    assert summary["raw_worker_death_events"] == 1
    assert summary["zerg_structure_starts"] == 1
    assert summary["estimated_construction_consumed"] == 1
    assert summary["estimated_worker_losses"] == 0


def test_resource_float_is_grouped_and_bounded_by_state():
    extraction = _extraction()
    extraction["tracker_events"] = [
        event for event in extraction["tracker_events"]
        if not (event.get("event_type") == "PlayerStats" and event.get("player_id") == 1)
    ]
    extraction["tracker_events"].extend(
        [
            _event("float-1", "PlayerStats", 480, player_id=1, stats={"workers_active_count": 30, "food_used": 60, "food_made": 80, "minerals_current": 700, "vespene_current": 100}),
            _event("float-2", "PlayerStats", 640, player_id=1, stats={"workers_active_count": 35, "food_used": 80, "food_made": 80, "minerals_current": 900, "vespene_current": 500}),
            _event("float-3", "PlayerStats", 800, player_id=1, stats={"workers_active_count": 40, "food_used": 100, "food_made": 100, "minerals_current": 1500, "vespene_current": 600}),
            _event("float-4", "PlayerStats", 1200, player_id=1, stats={"workers_active_count": 42, "food_used": 100, "food_made": 120, "minerals_current": 1300, "vespene_current": 550}),
            _event("float-5", "PlayerStats", 1400, player_id=1, stats={"workers_active_count": 42, "food_used": 100, "food_made": 120, "minerals_current": 400, "vespene_current": 100}),
        ]
    )
    facts = derive_facts(extraction)
    episodes = [item for item in facts["economy"]["float_episodes"] if item["player_id"] == 1]
    assert len(episodes) == 1
    episode = episodes[0]
    assert episode["start_loop"] == 640
    assert episode["end_loop"] == 1400
    assert episode["peak_loop"] == 800
    assert episode["peak_minerals"] == 1500
    assert episode["primary_constraint"] == "supply_blocked"
    assert episode["purchasing_power"]["Roach"]["resource_bound"] == 20
    assert episode["purchasing_power"]["Roach"]["supply_bound"] == 0
    assert episode["purchasing_power"]["Roach"]["immediate_upper_bound"] is None
    assert episode["meaningful"] is True
