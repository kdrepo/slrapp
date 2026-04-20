import json
import os
from json import JSONDecodeError
from pathlib import Path

import requests
from django.conf import settings

from reviews.models import Review
from reviews.services.prompt_loader import render_prompt_template
from reviews.services.scaffold_service import get_scaffold_data, get_theoretical_synthesis, set_scaffold_data


def generate_conceptual_model_spec(review_id):
    review = Review.objects.get(pk=review_id)
    scaffold = get_scaffold_data(review)
    themes = list(review.theme_syntheses.all().order_by('order_index', 'id'))
    if not themes:
        raise RuntimeError('No theme syntheses found. Run theme/dialectical phases first.')

    theoretical_synthesis = get_theoretical_synthesis(scaffold)
    propositions = theoretical_synthesis.get('propositions', [])
    subgroup_data = scaffold.get('subgroup_data', {})
    if not isinstance(subgroup_data, dict):
        subgroup_data = {}

    theoretical_framework = scaffold.get('theoretical_framework', {})
    if not isinstance(theoretical_framework, dict):
        theoretical_framework = {}

    primary_lens = str(
        theoretical_framework.get('primary_lens')
        or theoretical_framework.get('recommended')
        or 'Not specified'
    ).strip()
    if not primary_lens or primary_lens.lower() == 'not specified':
        raise RuntimeError('Primary theoretical lens is not confirmed yet. Confirm lens in Part 1 before running Part 2.')

    all_reconciled = []
    for t in themes:
        all_reconciled.append(
            {
                'theme_name': t.theme_name_locked,
                'evidence_grade': t.evidence_grade,
                'paper_count': t.paper_count,
                'reconciled_text': (t.reconciled_text or t.reconciler_notes or '').strip(),
            }
        )

    prompt = render_prompt_template(
        'phase_19_conceptual_model_spec.md',
        context={
            'primary_topic': review.title or '',
            'primary_theoretical_lens': primary_lens,
            'propositions_formatted': json.dumps(propositions, ensure_ascii=False, indent=2),
            'all_reconciled_texts_with_theme_names': json.dumps(all_reconciled, ensure_ascii=False, indent=2),
            'subgroup_data_formatted': json.dumps(subgroup_data, ensure_ascii=False, indent=2),
        },
    )
    if not prompt.strip():
        raise RuntimeError('Prompt file phase_19_conceptual_model_spec.md is missing or empty.')

    raw = _call_deepseek(prompt=prompt)
    spec = _parse_with_correction(raw)
    if not isinstance(spec, dict):
        raise RuntimeError('Conceptual model output must be a JSON object.')
    _validate_spec(spec)

    graph_payload = _extract_graph_payload(spec)
    generated = _persist_json_outputs(review_id=review.id, spec=spec, graph_payload=graph_payload)

    scaffold['conceptual_model_spec'] = spec
    scaffold['conceptual_model_narrative'] = str(spec.get('model_narrative') or '').strip()
    scaffold['conceptual_model_graph_payload'] = graph_payload
    set_scaffold_data(review, scaffold)
    review.save(update_fields=['scaffold_data'])

    return {
        'node_count': _node_count(spec),
        'relationship_count': len(spec.get('relationships') or []),
        'generated': generated,
    }


def _persist_json_outputs(review_id, spec, graph_payload):
    assets_dir = Path(settings.MEDIA_ROOT) / 'visual_assets' / str(review_id)
    assets_dir.mkdir(parents=True, exist_ok=True)

    spec_path = assets_dir / 'figure_conceptual_model_spec.json'
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding='utf-8')

    graph_path = assets_dir / 'figure_conceptual_model_graph_payload.json'
    graph_path.write_text(json.dumps(graph_payload, ensure_ascii=False, indent=2), encoding='utf-8')

    return [spec_path.name, graph_path.name]


def _extract_graph_payload(spec):
    nodes = []
    ids = set()

    def _push(node, ntype):
        if not isinstance(node, dict):
            return
        nid = str(node.get('id') or '').strip()
        if not nid or nid in ids:
            return
        ids.add(nid)
        nodes.append(
            {
                'id': nid,
                'label': str(node.get('label') or nid),
                'definition': str(node.get('definition') or ''),
                'evidence_grade': str(node.get('evidence_grade') or 'Emerging'),
                'type': ntype,
                'shape': _shape_for_type(ntype),
            }
        )

    _push(spec.get('main_outcome'), 'main_outcome')
    for key, ntype in [('antecedents', 'antecedent'), ('mediators', 'mediator'), ('moderators', 'moderator')]:
        for node in (spec.get(key) or []):
            _push(node, ntype)

    relationships = []
    for row in spec.get('relationships') or []:
        if not isinstance(row, dict):
            continue
        src = str(row.get('from') or '').strip()
        dst = str(row.get('to') or '').strip()
        if not src or not dst:
            continue
        relationships.append(
            {
                'from': src,
                'to': dst,
                'relationship_type': str(row.get('relationship_type') or 'direct'),
                'direction': str(row.get('direction') or 'unknown'),
                'evidence_grade': str(row.get('evidence_grade') or 'Emerging'),
                'label': str(row.get('label') or ''),
                'key_papers': row.get('key_papers') if isinstance(row.get('key_papers'), list) else [],
            }
        )

    moderating_relationships = []
    for row in spec.get('moderating_relationships') or []:
        if not isinstance(row, dict):
            continue
        on_rel = row.get('on_relationship') if isinstance(row.get('on_relationship'), dict) else {}
        moderator_id = str(row.get('moderator_id') or '').strip()
        on_from = str(on_rel.get('from') or '').strip()
        on_to = str(on_rel.get('to') or '').strip()
        if not moderator_id or not on_from or not on_to:
            continue
        moderating_relationships.append(
            {
                'moderator_id': moderator_id,
                'on_relationship': {'from': on_from, 'to': on_to},
                'direction': str(row.get('direction') or 'mixed'),
                'evidence_grade': str(row.get('evidence_grade') or 'Emerging'),
                'key_papers': row.get('key_papers') if isinstance(row.get('key_papers'), list) else [],
            }
        )

    return {
        'model_title': str(spec.get('model_title') or ''),
        'model_narrative': str(spec.get('model_narrative') or ''),
        'nodes': nodes,
        'relationships': relationships,
        'moderating_relationships': moderating_relationships,
        'visual_conventions': {
            'antecedent_shape': 'rectangle',
            'mediator_shape': 'oval',
            'main_outcome_shape': 'double_border_rectangle',
            'moderator_shape': 'diamond',
        },
    }


def _shape_for_type(ntype):
    if ntype == 'antecedent':
        return 'rectangle'
    if ntype == 'mediator':
        return 'oval'
    if ntype == 'main_outcome':
        return 'double_border_rectangle'
    return 'diamond'


def _node_count(spec):
    count = 0
    if isinstance(spec.get('main_outcome'), dict) and spec.get('main_outcome', {}).get('id'):
        count += 1
    for key in ['antecedents', 'mediators', 'moderators']:
        rows = spec.get(key) if isinstance(spec.get(key), list) else []
        count += sum(1 for item in rows if isinstance(item, dict) and str(item.get('id') or '').strip())
    return count


def _validate_spec(spec):
    main = spec.get('main_outcome')
    if not isinstance(main, dict) or not str(main.get('id') or '').strip():
        raise RuntimeError('Conceptual model spec missing valid main_outcome.id.')
    if not isinstance(spec.get('relationships'), list) or not spec.get('relationships'):
        raise RuntimeError('Conceptual model spec must contain at least one relationship.')


def _parse_with_correction(raw_response):
    try:
        return _extract_json(raw_response)
    except (JSONDecodeError, ValueError):
        correction_prompt = render_prompt_template(
            'phase_19_json_correction.md',
            context={'raw_response': raw_response},
        )
        if not correction_prompt.strip():
            raise RuntimeError('Prompt file phase_19_json_correction.md is missing or empty.')
        corrected = _call_deepseek(prompt=correction_prompt)
        return _extract_json(corrected)


def _call_deepseek(prompt):
    api_key = getattr(settings, 'DEEPSEEK_API_KEY', '') or os.getenv('DEEPSEEK_API_KEY', '')
    if not api_key:
        raise RuntimeError('DEEPSEEK_API_KEY is not configured.')

    base_url = (
        getattr(settings, 'DEEPSEEK_BASE_URL', '')
        or os.getenv('DEEPSEEK_BASE_URL', '')
        or 'https://api.deepseek.com'
    ).rstrip('/')
    model_name = (
        getattr(settings, 'DEEPSEEK_CONCEPTUAL_MODEL', '')
        or os.getenv('DEEPSEEK_CONCEPTUAL_MODEL', '')
        or 'deepseek-reasoner'
    )
    timeout_seconds = float(getattr(settings, 'DEEPSEEK_TIMEOUT_SECONDS', 120))

    response = requests.post(
        f'{base_url}/chat/completions',
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json={
            'model': model_name,
            'messages': [
                {'role': 'system', 'content': 'Return only valid JSON.'},
                {'role': 'user', 'content': prompt},
            ],
            'temperature': 0.0,
        },
        timeout=timeout_seconds,
    )
    if response.status_code >= 400:
        raise RuntimeError(f'DeepSeek HTTP {response.status_code}: {response.text[:1000]}')

    data = response.json()
    choices = data.get('choices') or []
    if not choices:
        raise RuntimeError('DeepSeek response missing choices.')
    message = choices[0].get('message') or {}
    content = message.get('content')
    if isinstance(content, list):
        merged = []
        for part in content:
            if isinstance(part, dict) and part.get('type') == 'text':
                merged.append(part.get('text') or '')
            elif isinstance(part, str):
                merged.append(part)
        content = '\n'.join(merged)

    text = (content or '').strip()
    if not text:
        raise RuntimeError('DeepSeek returned empty conceptual model content.')
    return text


def _extract_json(raw_text):
    text = (raw_text or '').strip()
    if text.startswith('```'):
        text = text.strip('`')
        text = text.replace('json\n', '', 1).strip()

    try:
        return json.loads(text)
    except JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char not in '[{':
                continue
            try:
                parsed, _ = decoder.raw_decode(text[index:])
                return parsed
            except JSONDecodeError:
                continue
        raise
