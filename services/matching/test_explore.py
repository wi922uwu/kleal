# -*- coding: utf-8 -*-
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "shared"))
sys.path.insert(0, HERE)

import app


class ExplorePlansTest(unittest.TestCase):
    def setUp(self):
        self.original_load_candidates = app.load_candidates
        self.original_session = app.SESSION
        app.SESSION = {"_intents": []}

    def tearDown(self):
        app.load_candidates = self.original_load_candidates
        app.SESSION = self.original_session

    def plans(self, users, profile=None):
        app.load_candidates = lambda: users
        return app.explore_plans(
            limit=20,
            self_name="Viewer",
            viewer_profile=profile,
        )

    def test_interests_without_an_intent_are_not_a_plan(self):
        users = [{
            "name": "Host",
            "source": "onboarding",
            "interests": ["coding"],
            "intents": [],
        }]
        self.assertEqual([], self.plans(users))

    def test_seed_intents_are_never_public(self):
        users = [{
            "name": "Seed Host",
            "source": "seed",
            "intents": [{"status": "active", "topics": ["coffee"]}],
        }]
        self.assertEqual([], self.plans(users))

    def test_real_intent_preserves_only_stored_facts(self):
        users = [{
            "name": "Host",
            "age": 30,
            "source": "onboarding",
            "city": "Barcelona",
            "intents": [{
                "id": "intent-1",
                "status": "active",
                "title": "Coffee after work",
                "topics": ["coffee"],
                "when": "Friday 19:00",
            }],
        }]
        plans = self.plans(users)
        self.assertEqual(1, len(plans))
        self.assertEqual("intent-1", plans[0]["intentId"])
        self.assertEqual("Friday 19:00", plans[0]["when"])
        self.assertEqual("Barcelona", plans[0]["area"])
        self.assertNotIn("dist", plans[0])
        self.assertNotIn("lat", plans[0])
        self.assertNotIn("lon", plans[0])

    def test_home_feed_requires_relevance_and_owner_permission(self):
        users = [{
            "name": "Coffee Host",
            "source": "onboarding",
            "intents": [{
                "status": "active",
                "topics": ["coffee"],
                "minAge": 20,
                "maxAge": 28,
            }],
        }, {
            "name": "Football Host",
            "source": "onboarding",
            "intents": [{"status": "active", "topics": ["football"]}],
        }]
        profile = {"name": "Viewer", "age": 24, "interests": ["coffee"]}
        plans = self.plans(users, profile)
        self.assertEqual(["Coffee Host"], [plan["who"] for plan in plans])

        profile["age"] = 29
        self.assertEqual([], self.plans(users, profile))

    def test_inactive_intents_are_not_public(self):
        users = [{
            "name": "Host",
            "source": "onboarding",
            "intents": [
                {"status": "completed", "topics": ["coffee"]},
                {"status": "draft", "topics": ["football"]},
            ],
        }]
        self.assertEqual([], self.plans(users))

    def test_saved_intent_is_visible_without_owner_in_candidate_pool(self):
        app.SESSION["_intents"] = [{
            "id": "saved-1",
            "owner": "ПЕРФОРАТОР",
            "title": "Programming practice",
            "intent": {
                "topics": ["programming", "coding"],
                "role": "practise",
                "place": "Barcelona",
            },
        }]
        profile = {
            "name": "Иван",
            "age": 28,
            "interests": ["coding", "programming", "development"],
        }

        plans = self.plans([], profile)

        self.assertEqual(1, len(plans))
        self.assertEqual("saved-1", plans[0]["intentId"])
        self.assertEqual("ПЕРФОРАТОР", plans[0]["who"])
        self.assertEqual("Programming practice", plans[0]["title"])
        self.assertEqual("Barcelona", plans[0]["area"])
        self.assertNotIn("dist", plans[0])

    def test_saved_intent_is_hidden_from_its_owner(self):
        app.SESSION["_intents"] = [{
            "id": "saved-1",
            "owner": "Viewer",
            "intent": {"topics": ["coding"]},
        }]
        profile = {"name": "Viewer", "interests": ["coding"]}

        self.assertEqual([], self.plans([], profile))

    def test_embedded_and_saved_intent_are_deduplicated_by_id(self):
        intent = {"id": "same-1", "status": "active", "topics": ["coding"]}
        app.SESSION["_intents"] = [{
            "id": "same-1",
            "owner": "Host",
            "intent": dict(intent),
        }]
        users = [{
            "name": "Host",
            "source": "onboarding",
            "intents": [dict(intent)],
        }]
        profile = {"name": "Viewer", "interests": ["coding"]}

        self.assertEqual(1, len(self.plans(users, profile)))

    def test_inactive_saved_intent_is_not_public(self):
        app.SESSION["_intents"] = [{
            "id": "saved-1",
            "owner": "Host",
            "status": "archived",
            "intent": {"topics": ["coding"]},
        }]
        profile = {"name": "Viewer", "interests": ["coding"]}

        self.assertEqual([], self.plans([], profile))


if __name__ == "__main__":
    unittest.main()
