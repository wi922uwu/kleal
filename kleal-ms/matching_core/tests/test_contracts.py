# -*- coding: utf-8 -*-
"""§4 canonical contracts — unit + property + purpose/safety tests (§23.3 DoD; C#3/#9/#12/#14/#24)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.contracts import (evidence as EV, profile as PR, intent as IN,
                                      receiving_policy as RP, proposal as PP, reservation as RS,
                                      match as MA, group as GR, plan as PL, relationship_edge as RE,
                                      decision_trace as DT, candidate as CA)

R = {"pass": 0, "fail": 0}


def check(name, cond):
    R["pass" if cond else "fail"] += 1
    print(("  ok  " if cond else " FAIL ") + name)


def run():
    # ---------- Evidence (§4.1/§4.2) ----------
    e1 = EV.build_evidence("interest.game", "Dota 2", "current_intent_explicit", scope="intent:i1")
    e_alias = EV.build_evidence("interest.game", "Dota 2", "current_intent_explicit", scope="intent:i1")
    check("EV1 alias одной фразы -> тот же evidence_id (§4.1)", e1["evidence_id"] == e_alias["evidence_id"])
    check("EV2 priority по источнику (§4.2)", e1["priority"] == 1)
    e_old = EV.build_evidence("interest.game", "LoL", "stable_profile_explicit", scope="prof")
    win = EV.resolve_field([e_old, e1], "interest.game")
    check("EV3 current_intent (p1) бьёт stable_profile (p4)", win["value"] == "Dota 2")
    # C#3: один raw evidence не даёт 4 независимых бонуса -> dedup схлопывает по id
    dup = EV.dedup([e1, e_alias, e_old])
    check("C#3 dedup: aliases одной фразы -> 1 evidence", len(dup) == 2)

    # ---------- ProfileView purpose binding (§8.3, Прил. D; C#12/#14) ----------
    user = PR.build_user_profile("u1", name="Ann", age=29, gender="f", orientation="straight",
                                 profession="designer", languages=["en", "es"],
                                 interests=["coffee", "chess"], dating_preferences={"age_range": [25, 35]},
                                 geo={"exact_lat": 41.11, "exact_lon": 2.22, "coarse_area": "Eixample",
                                      "coarse_lat": 41.4, "coarse_lon": 2.1}, city="Barcelona")
    vf = PR.build_profile_view(user, "friendship")
    vd = PR.build_profile_view(user, "dating")
    vn = PR.build_profile_view(user, "networking")
    # C#12: dating-поля НЕ в friendship/networking
    check("C#12 dating_preferences нет в friendship", "dating_preferences" not in vf["fields"])
    check("C#12 gender/orientation нет в friendship", "gender" not in vf["fields"] and "orientation" not in vf["fields"])
    check("C#12 dating_preferences ЕСТЬ в dating", "dating_preferences" in vd["fields"])
    # C#14: точная локация НИКОГДА не в view (ни в одном purpose)
    def no_exact(v):
        loc = v["fields"].get("location") or {}
        return "exact_lat" not in loc and "exact_lon" not in loc
    check("C#14 friendship view без точной локации", no_exact(vf))
    check("C#14 dating view без точной локации", no_exact(vd))
    check("C#14 coarse-зона присутствует", (vf["fields"].get("location") or {}).get("coarse_area") == "Eixample")
    # возраст: friendship -> band; dating без consent -> band; dating с consent -> точный
    check("PV1 friendship age -> band", vf["fields"].get("age_band") == "25-34" and "age" not in vf["fields"])
    vd_consent = PR.build_profile_view(user, "dating", consents={"consent_exact_age": True})
    check("PV2 dating+consent -> точный возраст", vd_consent["fields"].get("age") == 29)
    # профессия: networking core, dating drop
    check("PV3 profession в networking", vn["fields"].get("profession") == "designer")
    check("PV4 profession нет в dating (не implicit pref)", "profession" not in vd["fields"])

    # ---------- Intent (§4.3, §5.3) ----------
    it = IN.build_intent("i1", "u1", "games", activity="dota", topics=["dota2"], mode="online",
                         time={"windows": [["20:00", "23:00"]]}, expires_at=1000.0)
    check("IN1 build+validate", IN.validate_intent(it))
    check("IN2 flat", IN.flat(it)["domain"] == "games" and IN.flat(it)["topics"] == ["dota2"])
    v0 = it["identity"]["version"]
    check("IN3 bump_version инкрементит (§4.3)", IN.bump_version(it)["identity"]["version"] == v0 + 1)
    check("IN4 is_expired по TTL", IN.is_expired(it, 1000.0) and not IN.is_expired(it, 999.0))
    ok, missing = IN.minimal_intent_ok(it)
    check("IN5 minimal_intent_ok (§5.3)", ok is True and missing == [])
    bad = IN.build_intent("i2", "u1", "games")  # нет времени/ttl
    check("IN6 неполный intent -> missing", IN.minimal_intent_ok(bad)[0] is False)

    # ---------- ReceivingPolicy (§4.4) ----------
    rp = RP.build_receiving_policy("u2", allowed_domains=["social_meet"], paused_until=None,
                                   proposal_budget={"per_24h": 2, "per_7d": 5})
    check("RP1 allows_domain", RP.allows_domain(rp, "social_meet") and not RP.allows_domain(rp, "dating"))
    check("RP2 quiet hours (wrap midnight)", RP.in_quiet_hours(rp, 23 * 60) and not RP.in_quiet_hours(rp, 12 * 60))
    check("RP3 budget_ok", RP.budget_ok(rp, received_24h=1) and not RP.budget_ok(rp, received_24h=2))
    paused = RP.build_receiving_policy("u3", status="paused", paused_until=2000.0)
    check("RP4 is_paused", RP.is_paused(paused, 1500.0) and not RP.is_paused(paused, 2500.0))

    # ---------- Proposal / Reservation (§4; C#9) ----------
    pp = PP.build_proposal("p1", "a", "b", "i1", created_at=0.0, ttl_sec=720 * 60)
    check("PP1 idempotency_key присутствует (§23.2 п.13)", bool(pp["idempotency_key"]))
    check("C#9 expired proposal нельзя принять", PP.is_expired(pp, 720 * 60 + 1) and not PP.is_expired(pp, 10))
    try:
        PP.build_proposal("p2", "a", "b", "i1", status="bogus"); check("PP2 bad status -> raise", False)
    except ValueError:
        check("PP2 bad status -> raise", True)
    rsv = RS.build_reservation("r1", "group:g1:slot", "a", created_at=0.0, ttl_sec=1200)
    check("RS1 reservation expiry", RS.is_expired(rsv, 1201) and not RS.is_expired(rsv, 10))

    # ---------- Match / Group / Plan ----------
    m = MA.build_match("m1", ["a", "b"], "friendship.walk")
    check("MA1 match purpose_id", m["purpose_id"] == "friendship.walk" and m["status"] == "active")
    g = GR.build_group("g1", "a", size_min=4, pair_blocks=[("b", "c")])
    check("GR1 group pair_blocks нормализованы", ("b", "c") in g["pair_blocks"])
    try:
        PL.build_plan("pl1", ["a", "b"], place="Cafe", room="zoom"); check("PL1 place XOR room", False)
    except ValueError:
        check("PL1 place XOR room (§4)", True)
    pl = PL.build_plan("pl2", ["a", "b"], place="Cafe", state="confirmed")
    check("PL2 valid plan", pl["state"] == "confirmed" and pl["room"] is None)

    # ---------- RelationshipEdge (§4.12; scope isolation §8.3) ----------
    ed = RE.build_relationship_edge(["B", "a"], "friend", scope="friendship", last_ts=0.0)
    check("RE1 pair нормализована + scope", ed["pair"] == ("a", "b") and ed["scope"] == "friendship")
    check("RE2 cooldown", RE.in_cooldown(ed, 3 * 86400) and not RE.in_cooldown(ed, 8 * 86400))

    # ---------- decision_trace (§21.3; C#24 replay-ready) ----------
    tr = DT.build_decision_trace("s1", "u1", intent_version=7, policy={"decision": "ALLOW", "version": "pol-2.1.0"},
                                 semantic_tier="T1", config_version="matching-core-2.0.0",
                                 directional={"a_to_b": {"lcb": 0.7}, "b_to_a": {"lcb": 0.68}})
    replay_keys = {"intent_version", "config_version", "policy", "semantic_tier", "directional", "reason_keys"}
    check("C#24 decision_trace содержит все версии для replay", replay_keys.issubset(tr.keys())
          and tr["config_version"] == "matching-core-2.0.0")

    # ---------- CandidateSnapshot ----------
    cs = CA.build_candidate_snapshot("u1", source="active_intent_match", tier="T0", intent_version=7)
    check("CA1 snapshot версионирован", cs["semantic_tier"] == "T0" and cs["versions"]["intent"] == 7)

    print("\n§4 contracts: %d passed, %d failed" % (R["pass"], R["fail"]))
    return R["fail"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
