#!/usr/bin/env python3
"""Observable evidence-state regressions; no imports from production helpers.

--case selects one correction for disposable mutation controls. Fixtures are
current inspect-shaped data, held constant except the stated field mutation.
"""
import argparse
from copy import deepcopy
import itertools
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
COMP = ROOT / 'resources/compare_inspections.py'
BASE = json.loads((ROOT / 'resources/tests/fixtures/ghp-0.0.5.json').read_text())
MISSING = object()
CASES = 0


def play(value):
    return value['data']['play_inspect']


def pair(same=False):
    old, new = deepcopy(BASE), deepcopy(BASE)
    if not same:
        play(new)['identity']['version'] = '0.0.6'
    return old, new


def set_value(wrapper, path, value):
    obj = play(wrapper)
    parts = path.split('.')
    for part in parts[:-1]:
        obj = obj[part]
    if value is MISSING:
        obj.pop(parts[-1], None)
    else:
        obj[parts[-1]] = deepcopy(value)


def compare(old, new):
    global CASES
    run = subprocess.run([sys.executable, str(COMP), json.dumps(old), json.dumps(new)],
                         text=True, capture_output=True, timeout=20)
    assert run.returncode == 0, run.stderr or run.stdout
    result = json.loads(run.stdout)
    assert result['reviewed_plays_executed'] is False
    assert result['reason_codes'] == sorted(set(result['reason_codes']))
    assert len(run.stdout.encode()) <= 32768
    CASES += 1
    return result


def incomplete(result, domain):
    assert result['verdict'] == 'COMPARISON_INCOMPLETE', result
    assert result['inspection_coverage']['comparison_complete'] is False
    assert result['inspection_coverage']['domains'][domain]['comparable'] is False
    assert not any(c['material'] for c in result['changes']), result
    assert result['counts']['material_findings'] == 0
    assert result['counts']['total_findings'] == len(result['changes'])


def test_collections():
    domains = ['parameters', 'steps', 'requirements.write_permissions', 'requirements.runtimes',
               'requirements.npm_packages', 'requirements.browser_binaries',
               'requirements.endpoints', 'authentication.adapters', 'package.files', 'package.tools']
    bad = [MISSING, None, '', {}, False, 0]
    for domain in domains:
        old, new = pair(same=True)
        set_value(old, domain, []); set_value(new, domain, [])
        result = compare(old, new)
        assert result['verdict'] == 'EXACT_MATCH', (domain, result)
        assert result['inspection_coverage']['domains'][domain]['comparable'] is True
        for value in bad:
            for a, b in ((value, []), ([], value), (value, value)):
                old, new = pair(same=True)
                set_value(old, domain, a); set_value(new, domain, b)
                result = compare(old, new); incomplete(result, domain)
                if domain == 'steps':
                    assert result['inspection_coverage']['execution_step_fields_compared'] == []
                    assert result['approved']['step_count'] is None
        for member in (None, False, 0, {}, []):
            old, new = pair();set_value(old, domain, [member]);set_value(new, domain, [])
            incomplete(compare(old, new), domain)
    for domain in ('parameters', 'steps'):
        old, new = pair();play(new)[domain][0]['name'] = ''
        incomplete(compare(old, new), domain)
    for parent in ('requirements', 'authentication', 'package', 'execution'):
        for value in bad:
            old, new = pair(same=True);set_value(old, parent, value);set_value(new, parent, value)
            result = compare(old, new)
            assert result['verdict'] == 'COMPARISON_INCOMPLETE', (parent, value, result)
    old = {'ok': True, 'data': {'play_inspect': {'identity': {'owner': 'audit', 'name': 'fixture', 'version': '1.0.0'}}}}
    result = compare(old, old)
    assert result['verdict'] == 'COMPARISON_INCOMPLETE'
    assert result['comparison_performed'] is False
    assert result['declared_access_expansion_observed'] is None
    assert result['disclosure_unknowns']
    # Valid root dependency and optional parameter-default omission conventions.
    old, new = pair(same=True)
    play(old)['steps'] = [dict(name='root', kind='process.exec', target='process/local', operation='process.exec')]
    play(new)['steps'] = deepcopy(play(old)['steps']);play(new)['steps'][0]['depends_on'] = []
    assert compare(old, new)['verdict'] == 'EXACT_MATCH'
    for field in ('credential_names', 'protocols'):
        old, new = pair()
        entry = dict(adapter='api', credential_names=[], protocols=[])
        play(old)['authentication']['adapters'] = [deepcopy(entry)]
        play(new)['authentication']['adapters'] = [deepcopy(entry)]
        for value in bad:
            set_value(old, 'authentication.adapters', [dict(entry, **{field: value if value is not MISSING else None})])
            result = compare(old, new);incomplete(result, 'authentication.' + field)
            assert result['declared_access_expansion_observed'] is None
    old, new = pair(same=True)
    assert compare(old, new)['verdict'] == 'EXACT_MATCH'


def test_tools():
    for required in (False, True):
        for field, a, b in [('command', 'python3', 'python3.13'),
                            ('version_requirement', '>=3.8', '>=3.13')]:
            for reverse in (False, True):
                old, new = pair()
                tool = dict(id='python', command='python3', required=required)
                play(old)['package']['tools'] = [dict(tool, **{field: b if reverse else a})]
                play(new)['package']['tools'] = [dict(tool, **{field: a if reverse else b})]
                result = compare(old, new)
                assert result['reason_codes'] == ['TOOL_REQUIREMENT_CHANGED'], result
                assert result['changes'][0]['material'] is required
                assert result['counts']['material_findings'] == int(required)
                assert result['counts']['material_types'] == int(required)
                assert result['counts']['total_findings'] == 1
                assert result['verdict'] == ('MATERIAL_METHOD_CHANGE' if required else 'NO_MATERIAL_VISIBLE_CHANGE_OBSERVED')
        for addition in (False, True):
            old, new = pair();tool = dict(id='extra', command='extra', required=required)
            play(old)['package']['tools'] = [] if addition else [tool]
            play(new)['package']['tools'] = [tool] if addition else []
            result = compare(old, new)
            code = 'TOOL_REQUIREMENT_ADDED' if addition else 'TOOL_REQUIREMENT_REMOVED'
            assert result['reason_codes'] == [code]
            assert result['changes'][0]['material'] is required
            assert result['counts']['material_types'] == int(required)
            assert result['counts']['material_findings'] == int(required)
            assert result['verdict'] == ('MATERIAL_METHOD_CHANGE' if required else 'NO_MATERIAL_VISIBLE_CHANGE_OBSERVED')
        old, new = pair();tool = dict(id='python', command='python3', required=required)
        play(old)['package']['tools'] = [dict(tool, install_hints=['old advice'])]
        play(new)['package']['tools'] = [dict(tool, install_hints=['new advice'])]
        result = compare(old, new)
        assert result['counts']['material_findings'] == 0
        assert result['verdict'] == 'NO_MATERIAL_VISIBLE_CHANGE_OBSERVED'
    for a, b in ((True, False), (False, True)):
        old, new = pair();play(old)['package']['tools'][0]['required'] = a;play(new)['package']['tools'][0]['required'] = b
        result = compare(old, new)
        assert result['reason_codes'] == ['TOOL_REQUIREMENT_CHANGED']
        assert result['changes'][0]['material'] is True
        assert result['counts']['material_types'] == result['counts']['material_findings'] == 1
        assert result['verdict'] == 'MATERIAL_METHOD_CHANGE'


def test_artifacts():
    for path, prefix in [('archive.content_hash', ''), ('package.digest', 'installed-package-sha256-v1:')]:
        values = [MISSING, None, '', ' ', False, 0, {}, [], 'unrecognized:abc', prefix+'a'*64, prefix+'b'*64]
        for same in (False, True):
            for i, j in itertools.product(range(len(values)), repeat=2):
                old, new = pair(same);set_value(old, path, values[i]);set_value(new, path, values[j])
                result = compare(old, new)
                valid = i >= 9 and j >= 9
                changed = valid and i != j
                code = 'IMMUTABLE_RELEASE_IDENTITY_CHANGED' if same else 'IMPLEMENTATION_CHANGED'
                assert (code in result['reason_codes']) == changed, (path, i, j, result)
                if not valid:
                    incomplete(result, path)
                    assert 'IMMUTABLE_RELEASE_VISIBLE_STATE_CHANGED' not in result['reason_codes']
                elif changed:
                    assert result['verdict'] == ('INTEGRITY_ANOMALY' if same else 'IMPLEMENTATION_CHANGED_SAME_VISIBLE_CONTRACT')
                else:
                    assert result['verdict'] == ('EXACT_MATCH' if same else 'NO_MATERIAL_VISIBLE_CHANGE_OBSERVED')
        old, new = pair(same=True);set_value(old,path,prefix+'A'*64);set_value(new,path,prefix+'a'*64)
        assert compare(old,new)['verdict'] == 'EXACT_MATCH'


def test_privileges():
    states = {'none': set(), 'browser': {'browser'}, 'process': {'process'},
              'process_and_browser': {'process', 'browser'}}
    path = 'execution.privileged_access'
    for a, b in itertools.product(states, repeat=2):
        old, new = pair();set_value(old,path,a);set_value(new,path,b);result=compare(old,new)
        assert result['declared_access_expansion_observed'] is bool(states[b]-states[a])
        assert result['counts']['material_findings'] == int(a!=b)
        assert ('PRIVILEGED_ACCESS_CHANGED' in result['reason_codes']) == (a!=b)
    unknown = [MISSING, None, '', ' ', 'future-capability', False, 0, {}, []]
    for value in unknown:
        for known in states:
            for a, b in ((value,known),(known,value)):
                old,new=pair();set_value(old,path,a);set_value(new,path,b);result=compare(old,new)
                incomplete(result,path)
                assert result['declared_access_expansion_observed'] is None
                assert result['inspection_coverage']['access_comparison_complete'] is False
                assert 'PRIVILEGED_ACCESS_CHANGED' not in result['reason_codes']
        old,new=pair(same=True);set_value(old,path,value);set_value(new,path,value)
        result=compare(old,new);incomplete(result,path)
        assert result['declared_access_expansion_observed'] is None


def test_type():
    for a,b in [('string','integer'),('integer','string')]:
        old,new=pair();play(old)['parameters'][0]['type']=a;play(new)['parameters'][0]['type']=b
        result=compare(old,new)
        assert result['reason_codes']==['PARAMETER_TYPE_CHANGED']
        assert result['changes'][0]['material'] is True
        assert result['counts']['material_types']==result['counts']['material_findings']==1
        assert result['verdict']=='MATERIAL_METHOD_CHANGE'


TESTS = {'PCR-01': test_collections, 'PCR-02': test_tools, 'PCR-03': test_artifacts,
         'PCR-04': test_privileges, 'TEST-01': test_type}
if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--case',choices=TESTS);args=parser.parse_args()
    for name,test in TESTS.items():
        if args.case and args.case != name:continue
        before=CASES;test();print(f'PASS {name}: {CASES-before} observable comparisons',flush=True)
    print(f'ALL {CASES} EVIDENCE-CONTRACT COMPARISONS PASSED')
