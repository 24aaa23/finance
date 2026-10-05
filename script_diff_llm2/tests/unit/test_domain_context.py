import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from script_diff_llm.pipeline.domain_context import (
    append_domain_context, prepare_domain_context, relevant_domain_entries, validate_entries,
    parse_preparation_response,
)
from script_diff_llm.pipeline.decomposition import semantic_decompose
from script_diff_llm.pipeline.specification import semantic_build_query_spec
from tests.unit.test_portable_contracts import SCHEMA, QUESTION, spec


def client_for(value):
    create = Mock(return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(value)))]))
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def entry(**changes):
    return dict(id='amount', document='domain_intro', kind='definition', topic='amount',
                backend='sql', source='charges', fields=['amount'], terms=['charge'],
                definition='Amount is measured in credits.', quote='Amount is measured in credits.',
                conflicts=[], **changes)


class DomainContextTest(unittest.TestCase):
    def test_parser_handles_reasoning_fences_and_preamble(self):
        body = json.dumps({'entries': [entry()]})
        for raw in (body, 'Here is the context:\n```json\n' + body + '\n```',
                    '<think>{"entries": []}</think>\n' + body,
                    '<|channel|>analysis<|message|>thinking<|channel|>final<|message|>' + body):
            self.assertEqual(parse_preparation_response(raw)['entries'], [entry()])
        for raw in (None, '', '<think>unfinished', body[:-2], body + body, '{"fields": []}'):
            with self.assertRaises(ValueError):
                parse_preparation_response(raw)

    def test_preparation_retry_recovers_and_saves_diagnostics(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'intro').write_text('Amount is measured in credits.')
            candidate = entry()
            candidate['kind'] = 'terminology'
            client = client_for({})
            replies = ['', '<think>analysis</think>```json\n' + json.dumps({'entries': [candidate]}) + '\n```']
            client.chat.completions.create.side_effect = lambda **kwargs: SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=replies.pop(0)), finish_reason='stop')])
            context = prepare_domain_context(root, SCHEMA, {}, client, 'test', environ={
                'DOMAIN_INTRO_FILE': 'intro', 'DOMAIN_CONTEXT_REQUIRED': '1'})
            self.assertEqual(len(context['entries']), 1)
            self.assertEqual(client.chat.completions.create.call_count, 2)
            self.assertTrue(list(Path(root, 'outputs/domain_context').glob('*.failure.json')))

    def test_required_context_stops_on_failure_and_on_no_active_entries(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'intro').write_text('Amount is measured in credits.')
            env = {'DOMAIN_INTRO_FILE': 'intro', 'DOMAIN_CONTEXT_REQUIRED': '1'}
            for response in ({}, {'entries': [entry()]}):
                with self.assertRaises(RuntimeError):
                    prepare_domain_context(root, SCHEMA, {}, client_for(response), 'test', environ=env)
            with self.assertRaises(RuntimeError):
                prepare_domain_context(root, SCHEMA, {}, client_for({}), 'test', environ={'DOMAIN_CONTEXT_REQUIRED': '1'})

    def test_truncated_response_is_not_activated(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'intro').write_text('Amount is measured in credits.')
            candidate = entry()
            candidate['kind'] = 'terminology'
            client = client_for({'entries': [candidate]})
            client.chat.completions.create.return_value.choices[0].finish_reason = 'length'
            with self.assertRaises(RuntimeError):
                prepare_domain_context(root, SCHEMA, {}, client, 'test', environ={
                    'DOMAIN_INTRO_FILE': 'intro', 'DOMAIN_CONTEXT_REQUIRED': '1'})

    def test_reasoning_only_truncation_retries_with_larger_budget_and_caches(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'intro').write_text('Amount is measured in credits.')
            candidate = entry()
            candidate['kind'] = 'terminology'
            client = client_for({})
            client.chat.completions.create.side_effect = [
                SimpleNamespace(choices=[SimpleNamespace(
                    message=SimpleNamespace(content=None), finish_reason='length')]),
                SimpleNamespace(choices=[SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps({'entries': [candidate]})),
                    finish_reason='stop')]),
            ]
            env = {'DOMAIN_INTRO_FILE': 'intro', 'DOMAIN_CONTEXT_REQUIRED': '1',
                   'DOMAIN_CONTEXT_MAX_TOKENS': '12000',
                   'DOMAIN_CONTEXT_RETRY_MAX_TOKENS': '24000'}
            context = prepare_domain_context(root, SCHEMA, {}, client, 'test', environ=env)
            self.assertEqual(len(context['entries']), 1)
            calls = client.chat.completions.create.call_args_list
            self.assertEqual([call.kwargs['max_tokens'] for call in calls], [12000, 24000])
            self.assertIn('at most six', calls[1].kwargs['messages'][0]['content'])
            diagnostic = json.loads(next(Path(root, 'outputs/domain_context').glob('*.failure.json')).read_text())
            self.assertIsNone(diagnostic['attempts'][0]['content'])
            self.assertEqual(diagnostic['attempts'][0]['max_tokens'], 12000)
            cached = prepare_domain_context(root, SCHEMA, {}, client, 'test', environ=env)
            self.assertEqual(context['entries'], cached['entries'])
            self.assertEqual(client.chat.completions.create.call_count, 2)

    def test_dedicated_glossary_recovers_policy_only_preparation(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'intro').write_text('Amount is measured in credits.')
            policy = entry()
            policy['source'] = ['charges']
            policy['fields'] = ['logical.amount']
            glossary = entry()
            glossary['kind'] = 'terminology'
            client = client_for({})
            replies = [{'entries': [policy]}, {'entries': [glossary]}]
            client.chat.completions.create.side_effect = lambda **kwargs: SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(replies.pop(0))))])
            env = {'DOMAIN_INTRO_FILE': 'intro', 'DOMAIN_CONTEXT_REQUIRED': '1'}
            context = prepare_domain_context(root, SCHEMA, {}, client, 'test', environ=env)
            self.assertEqual([e['id'] for e in context['entries']], ['glossary:amount'])
            self.assertEqual(client.chat.completions.create.call_count, 2)
            cached = prepare_domain_context(root, SCHEMA, {}, client, 'test', environ=env)
            self.assertEqual(cached, context)
            self.assertEqual(client.chat.completions.create.call_count, 2)

    def test_numeric_policy_cannot_auto_activate_as_terminology(self):
        candidate = entry()
        candidate.update(kind='terminology', definition='Risk below 40 is low.', quote='Risk below 40 is low.')
        reviewed = validate_entries([candidate], {'domain_intro': {
            'text': 'Risk below 40 is low.', 'evaluation_scoped': False}}, {'sql': SCHEMA})
        self.assertEqual(reviewed[0]['kind'], 'definition')
        self.assertIn('classification_note', reviewed[0])

    def test_profile_ordering_does_not_invalidate_context_cache(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'intro').write_text('Amount is measured in credits.')
            candidate = entry()
            candidate['kind'] = 'terminology'
            client = client_for({'entries': [candidate]})
            original = copy.deepcopy(SCHEMA)
            original['charges']['samples'] = ['a', 'b']
            env = {'DOMAIN_INTRO_FILE': 'intro', 'DOMAIN_CONTEXT_REQUIRED': '1'}
            first = prepare_domain_context(root, original, {}, client, 'test', environ=env)
            reordered = copy.deepcopy(SCHEMA)
            reordered['charges']['column_names'].reverse()
            reordered['charges']['samples'] = ['different profiling values']
            second = prepare_domain_context(root, reordered, {}, client, 'test', environ=env)
            self.assertEqual(first, second)
            self.assertEqual(client.chat.completions.create.call_count, 1)

    def test_disabled_and_missing_make_no_calls(self):
        client = client_for({})
        with tempfile.TemporaryDirectory() as root:
            for env in ({}, {'DOMAIN_INTRO_FILE': 'missing'}, {'BUSINESS_RULES_FILE': 'missing'}):
                self.assertIsNone(prepare_domain_context(root, SCHEMA, {}, client, 'test', environ=env))
            self.assertEqual(list(Path(root).iterdir()), [])
        client.chat.completions.create.assert_not_called()
        self.assertEqual(append_domain_context('original prompt\n', []), 'original prompt\n')

    def test_cache_approval_and_schema_invalidation(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'intro').write_text('Amount is measured in credits.')
            env = {'DOMAIN_INTRO_FILE': 'intro'}
            client = client_for({'entries': [entry()]})
            self.assertIsNone(prepare_domain_context(root, SCHEMA, {}, client, 'test', environ=env))
            initial_calls = client.chat.completions.create.call_count
            cache = next(p for p in Path(root, 'outputs/domain_context').glob('*.json') if not p.name.endswith('.failure.json'))
            review = json.loads(cache.read_text())
            candidate = review['review'][0]
            approval = Path(root, 'approval.json')
            approval.write_text(json.dumps({'fingerprint': review['fingerprint'], 'approved': {candidate['id']: candidate['evidence_hash']}}))
            env['DOMAIN_CONTEXT_APPROVAL_FILE'] = 'approval.json'
            active = prepare_domain_context(root, SCHEMA, {}, client, 'test', environ=env)
            self.assertEqual(len(active['entries']), 1)
            self.assertEqual(client.chat.completions.create.call_count, initial_calls)
            self.assertEqual(relevant_domain_entries(active, 'average charge', 'sql', SCHEMA), active['entries'])
            self.assertEqual(relevant_domain_entries(active, 'chargeback', 'sql', SCHEMA), [])
            self.assertEqual(relevant_domain_entries(active, 'charge', 'kg', SCHEMA), [])
            self.assertEqual(relevant_domain_entries(active, 'charge', terminology_only=True), [])
            changed = copy.deepcopy(SCHEMA)
            changed['charges']['column_names'].remove('amount')
            self.assertIsNone(prepare_domain_context(root, changed, {}, client, 'test', environ=env))
            self.assertGreater(client.chat.completions.create.call_count, initial_calls)

    def test_evaluation_quotes_conflicts_and_unknown_fields_are_blocked(self):
        documents = {'domain_intro': {'text': 'Amount is measured in credits.', 'evaluation_scoped': False},
                     'business_rules': {'text': 'Amount is measured in credits.', 'evaluation_scoped': True}}
        for changes in ({'document': 'business_rules'}, {'quote': 'fabricated'},
                        {'fields': ['invented']}, {'conflicts': ['other definition']}):
            candidate = entry()
            candidate.update(changes)
            self.assertTrue(validate_entries([candidate], documents, {'sql': SCHEMA})[0]['errors'])
        conflicting = entry()
        conflicting['id'] = 'other'
        conflicting['definition'] = 'Amount means something else'
        self.assertTrue(all(e['errors'] for e in validate_entries([entry(), conflicting], documents, {'sql': SCHEMA})))

    def test_evaluation_scoped_file_cannot_be_approved(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'rules').write_text('Ground-truth corrections. Amount is measured in credits.')
            candidate = entry()
            candidate['document'] = 'business_rules'
            client = client_for({'entries': [candidate]})
            env = {'BUSINESS_RULES_FILE': 'rules'}
            self.assertIsNone(prepare_domain_context(root, SCHEMA, {}, client, 'test', environ=env))
            payload = json.loads(next(Path(root, 'outputs/domain_context').glob('*.json')).read_text())
            self.assertEqual(payload['review'], [])
            self.assertEqual(len(payload['quarantined_documents']), 1)
            client.chat.completions.create.assert_not_called()
            Path(root, 'approve').write_text(json.dumps({'fingerprint': payload['fingerprint'], 'approved': {'amount': 'anything'}}))
            env['DOMAIN_CONTEXT_APPROVAL_FILE'] = 'approve'
            self.assertIsNone(prepare_domain_context(root, SCHEMA, {}, client, 'test', environ=env))

    def test_quarantined_document_never_reaches_preparation_prompt(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'intro').write_text('Amount is measured in credits.')
            Path(root, 'rules').write_text('Ground-truth CORRECTION_SECRET')
            candidate = entry()
            candidate['kind'] = 'terminology'
            client = client_for({'entries': [candidate]})
            context = prepare_domain_context(root, SCHEMA, {}, client, 'test', environ={
                'DOMAIN_INTRO_FILE': 'intro', 'BUSINESS_RULES_FILE': 'rules'})
            self.assertIsNotNone(context)
            self.assertNotIn('CORRECTION_SECRET', client.chat.completions.create.call_args.kwargs['messages'][0]['content'])

    def test_bad_entry_does_not_disable_valid_terminology(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'intro').write_text('Amount is measured in credits.')
            good = entry()
            good['kind'] = 'terminology'
            malformed = {'quote': ['not a string'], 'definition': {'invalid': True}}
            client = client_for({'entries': [malformed, good]})
            context = prepare_domain_context(root, SCHEMA, {}, client, 'test', environ={'DOMAIN_INTRO_FILE': 'intro'})
            self.assertEqual([e['id'] for e in context['entries']], ['amount'])

    def test_missing_approval_keeps_valid_terminology(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'intro').write_text('Amount is measured in credits.')
            good = entry()
            good['kind'] = 'terminology'
            client = client_for({'entries': [good]})
            context = prepare_domain_context(root, SCHEMA, {}, client, 'test', environ={
                'DOMAIN_INTRO_FILE': 'intro', 'DOMAIN_CONTEXT_APPROVAL_FILE': 'missing'})
            self.assertEqual(len(context['entries']), 1)

    def test_changed_context_cannot_resume_existing_rows(self):
        from runners.check_domain_context_run import check_run
        with tempfile.TemporaryDirectory() as root:
            check_run(root, {'source': 'v1'})
            Path(root, 'raw_pipeline.csv').write_text('saved rows')
            check_run(root, {'source': 'v1'})
            with self.assertRaises(ValueError):
                check_run(root, {'source': 'v2'})
            self.assertEqual(json.loads(Path(root, 'domain_context_inputs.json').read_text()), {'source': 'v1'})

    def test_preparation_failure_falls_back(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'intro').write_text('Database context')
            client = client_for({})
            self.assertIsNone(prepare_domain_context(root, SCHEMA, {}, client, 'test', environ={'DOMAIN_INTRO_FILE': 'intro'}))

    def test_enabled_spec_gets_context_and_trace(self):
        candidate = entry()
        candidate.update(active=True, errors=[], evidence_hash='reviewed')
        client = client_for(spec())
        result = semantic_build_query_spec(
            {'query': QUESTION, 'root_query': QUESTION, 'schema_kind': 'sql',
             'retrieved_tables': list(SCHEMA), 'schema_details': SCHEMA, 'global_schema': SCHEMA,
             'domain_context': {'fingerprint': 'source-version', 'entries': [candidate]}},
            client, 'test', parse_json_fn=lambda raw, *_: json.loads(raw),
            normalize_for_compare_fn=str.lower, log_call_fn=lambda *_: None)
        self.assertIn('Amount is measured in credits.', client.chat.completions.create.call_args.kwargs['messages'][0]['content'])
        self.assertEqual(result['query_spec']['domain_context_trace']['fingerprint'], 'source-version')

    def test_context_reaches_kg_spec_and_all_contract_repairs(self):
        for backend in ('sql', 'kg'):
            with self.subTest(backend=backend):
                candidate = entry()
                candidate.update(backend=backend, active=True, errors=[], evidence_hash='reviewed')
                valid = spec()
                valid['execution_strategy'] = 'preaggregate_sql' if backend == 'sql' else 'preaggregate_sparql'
                invalid = copy.deepcopy(valid)
                invalid['measures'][0]['field'] = 'invented'
                client = client_for(valid)
                responses = [invalid, valid]
                client.chat.completions.create.side_effect = lambda **kwargs: SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(responses.pop(0))))])
                result = semantic_build_query_spec(
                    {'query': QUESTION, 'root_query': QUESTION, 'schema_kind': backend,
                     'global_schema': SCHEMA, 'retrieved_tables': list(SCHEMA),
                     'domain_context': {'fingerprint': 'source-version', 'entries': [candidate]}},
                    client, 'test', parse_json_fn=lambda raw, *_: json.loads(raw),
                    normalize_for_compare_fn=str.lower, log_call_fn=lambda *_: None)
                self.assertEqual(result['query_spec']['contract_errors'], [])
                self.assertEqual(client.chat.completions.create.call_count, 2)
                for call in client.chat.completions.create.call_args_list:
                    self.assertIn('Amount is measured in credits.', call.kwargs['messages'][0]['content'])

    def test_decomposition_gets_terminology_but_not_policy(self):
        terminology = entry()
        terminology.update(kind='terminology', definition='TERM_SENTINEL')
        policy = entry()
        policy.update(id='policy', definition='POLICY_SENTINEL')
        client = client_for({'nodes': []})
        semantic_decompose({'query': QUESTION, 'domain_context': {'entries': [terminology, policy]}},
                           client, 'test', lambda raw, *_: json.loads(raw))
        prompt = client.chat.completions.create.call_args.kwargs['messages'][0]['content']
        self.assertIn('TERM_SENTINEL', prompt)
        self.assertNotIn('POLICY_SENTINEL', prompt)

    def test_off_mode_operator_requests_and_outputs_equal_legacy(self):
        def run_spec():
            client = client_for(spec())
            result = semantic_build_query_spec(
                {'query': QUESTION, 'root_query': QUESTION, 'schema_kind': 'sql',
                 'retrieved_tables': list(SCHEMA), 'schema_details': SCHEMA, 'global_schema': SCHEMA},
                client, 'test', parse_json_fn=lambda raw, *_: json.loads(raw),
                normalize_for_compare_fn=str.lower, log_call_fn=lambda *_: None)
            return client.chat.completions.create.call_args_list, result
        actual = run_spec()
        with patch('script_diff_llm.pipeline.specification.append_domain_context', side_effect=lambda prompt, entries: prompt):
            legacy = run_spec()
        self.assertEqual(actual, legacy)
        def run_decompose():
            client = client_for({'nodes': [{'id': 'Q1', 'description': QUESTION, 'operator': 'Subquery'}]})
            result = semantic_decompose({'query': QUESTION, 'schema_context': SCHEMA}, client, 'test', lambda raw, *_: json.loads(raw))
            return client.chat.completions.create.call_args_list, result
        actual = run_decompose()
        with patch('script_diff_llm.pipeline.decomposition.append_domain_context', side_effect=lambda prompt, entries: prompt):
            legacy = run_decompose()
        self.assertEqual(actual, legacy)


if __name__ == '__main__':
    unittest.main()
