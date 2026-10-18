#!/usr/bin/env python3
"""Offline follow-through: JSON emitted by the real frontend handler -> real matching.

Usage: node kleal-app/tools/interest_hierarchy_test.js --json |
       python kleal-ms/tools/interest_hierarchy_check.py
No HTTP, database or model calls. Only synthetic keys in a temporary store.
"""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
fixtures = json.load(sys.stdin)
assert fixtures and fixtures[0]['selected'] == ['padel'], 'expected actual handler fixtures'
with tempfile.TemporaryDirectory(prefix='kleal_interest_hierarchy_') as directory:
    os.environ.update(KLEAL_DB='json', KLEAL_STORE=directory + '/store.json',
                      KLEAL_MONETIZATION_MODE='off', KLEAL_GEOCODE_ENABLED='0')
    sys.path[:0] = [str(ROOT / 'services' / 'matching'), str(ROOT / 'services' / 'onboarding')]
    spec = importlib.util.spec_from_file_location('hierarchy_matching_fixture', ROOT / 'services' / 'matching' / 'app.py')
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    import interest_normalization
    for fixture in fixtures:
        selected, stored = fixture['selected'], fixture['stored']
        assert fixture['displayed'] == selected
        if selected[0] == 'padel':
            assert set(stored) == {'sports', 'racket', *selected}
            assert all(interest_normalization.trusted_interest(key) for key in stored)
            for query in ('sports', 'racket', 'padel'):
                assert app.topical([query], stored)[0] == 4, (query, stored)
            assert app.topical(['games'], stored)[0] == 0, 'no unrelated broad match'
        else:
            assert stored == selected, 'no invented ancestry'
    print('PASS actual frontend handler -> backend trusted registry + matching: sports/racket/padel found; games unrelated; unknown keys unchanged')
