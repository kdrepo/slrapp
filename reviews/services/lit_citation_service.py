import json
import os
import re
from json import JSONDecodeError
from urllib.parse import quote

import requests
from django.conf import settings

from reviews.models import LitReview


DEEPSEEK_APA_NORMALIZER_SYSTEM_PROMPT = """You are an APA 7 citation normalizer.
You will receive:
1) trusted metadata
2) a draft citation string

Return only valid JSON with key: citation_apa.

Rules:
- Keep facts grounded in provided metadata only.
- Do not invent missing fields.
- Preserve DOI as https://doi.org/<doi> when present.
- Output one citation string only.
"""


def generate_apa_citations_for_lit_review(*, review_id, only_missing=True, progress_callback=None, stop_check=None):
    review = LitReview.objects.get(pk=review_id)
    papers_qs = review.papers.order_by('id')
    if only_missing:
        papers_qs = papers_qs.filter(citation_apa='')

    papers = list(papers_qs)
    done = 0
    failed = 0
    processed_ids = []

    _emit(
        progress_callback,
        {
            'event': 'started',
            'targeted': len(papers),
            'paper_ids': [paper.id for paper in papers],
        },
    )

    for index, paper in enumerate(papers, start=1):
        if stop_check and stop_check():
            _emit(progress_callback, {'event': 'stopped', 'processed_ids': list(processed_ids)})
            break
        _emit(
            progress_callback,
            {
                'event': 'processing',
                'paper_id': paper.id,
                'title': paper.title,
                'index': index,
                'targeted': len(papers),
            },
        )
        try:
            result = _build_citation_with_layered_fallback(paper)
            citation = (result.get('citation_apa') or '').strip()
            if not citation:
                raise RuntimeError('Citation output empty.')

            paper.citation_apa = citation
            paper.citation_status = 'done'
            paper.citation_error = ''
            paper.citation_source = (result.get('citation_source') or 'fallback')[:32]
            paper.save(update_fields=['citation_apa', 'citation_status', 'citation_error', 'citation_source'])
            done += 1
            processed_ids.append(paper.id)
            _emit(
                progress_callback,
                {
                    'event': 'done',
                    'paper_id': paper.id,
                    'title': paper.title,
                    'citation_source': paper.citation_source,
                },
            )
        except Exception as exc:
            paper.citation_status = 'failed'
            paper.citation_error = f'{exc.__class__.__name__}: {exc}'
            paper.citation_source = 'fallback'
            paper.save(update_fields=['citation_status', 'citation_error', 'citation_source'])
            failed += 1
            processed_ids.append(paper.id)
            _emit(
                progress_callback,
                {
                    'event': 'failed',
                    'paper_id': paper.id,
                    'title': paper.title,
                    'error_code': exc.__class__.__name__,
                    'error_message': str(exc),
                },
            )

    summary = {
        'targeted': len(papers),
        'done': done,
        'failed': failed,
        'processed_ids': processed_ids,
        'remaining_paper_ids': [paper.id for paper in papers if paper.id not in set(processed_ids)],
        'stopped': bool(stop_check and stop_check()),
    }
    _emit(progress_callback, {'event': 'completed', **summary})
    return summary


def _build_citation_with_layered_fallback(paper):
    base = _base_metadata_from_paper(paper)
    merged = dict(base)
    layer = 'local'

    # Layer 1: Crossref by DOI
    doi = _clean_doi(merged.get('doi'))
    if doi:
        crossref_doi = _crossref_by_doi(doi)
        if crossref_doi:
            merged = _merge_metadata(merged, crossref_doi)
            layer = 'crossref_doi'

    # Layer 2: Crossref by title
    if not _clean_doi(merged.get('doi')):
        crossref_title = _crossref_by_title(merged.get('title'))
        if crossref_title:
            merged = _merge_metadata(merged, crossref_title)
            layer = 'crossref_title'

    # Layer 3: Semantic Scholar by title
    if not _clean_doi(merged.get('doi')):
        semantic = _semantic_scholar_by_title(merged.get('title'))
        if semantic:
            merged = _merge_metadata(merged, semantic)
            layer = 'semantic_scholar'

    # Layer 4: Local/RIS metadata fallback already in base
    draft = _format_apa_from_metadata(merged)
    if not draft:
        raise RuntimeError('Could not construct draft citation from available metadata.')

    # Layer 5: LLM normalization (DeepSeek) on top of trusted metadata
    normalized = _normalize_with_deepseek_if_available(draft_citation=draft, metadata=merged)
    citation = normalized or draft
    source = f'{layer}+deepseek' if normalized else layer
    return {'citation_apa': citation, 'citation_source': source}


def _base_metadata_from_paper(paper):
    return {
        'title': (paper.title or '').strip(),
        'authors': _parse_local_authors((paper.authors or '').strip()),
        'year': _safe_year(paper.year),
        'source': (paper.source or '').strip(),
        'volume': '',
        'issue': '',
        'pages': '',
        'doi': _clean_doi((paper.doi or '').strip()),
        'url': (paper.url or '').strip(),
    }


def _crossref_by_doi(doi):
    if not doi:
        return {}
    url = f'https://api.crossref.org/works/{quote(doi, safe="")}'
    try:
        response = requests.get(url, headers={'Accept': 'application/json'}, timeout=30)
        if response.status_code >= 400:
            return {}
        payload = response.json()
        item = (payload.get('message') or {}) if isinstance(payload, dict) else {}
        return _metadata_from_crossref_item(item)
    except Exception:
        return {}


def _crossref_by_title(title):
    query = (title or '').strip()
    if not query:
        return {}
    url = f'https://api.crossref.org/works?query.title={quote(query)}&rows=1'
    try:
        response = requests.get(url, headers={'Accept': 'application/json'}, timeout=30)
        if response.status_code >= 400:
            return {}
        payload = response.json()
        items = (((payload.get('message') or {}).get('items')) or []) if isinstance(payload, dict) else []
        if not items:
            return {}
        return _metadata_from_crossref_item(items[0] or {})
    except Exception:
        return {}


def _semantic_scholar_by_title(title):
    query = (title or '').strip()
    if not query:
        return {}

    headers = {'Accept': 'application/json'}
    s2_api_key = (getattr(settings, 'S2_API_KEY', '') or os.getenv('S2_API_KEY', '')).strip()
    if s2_api_key:
        headers['x-api-key'] = s2_api_key

    fields = 'title,authors,year,venue,externalIds,url'
    url = f'https://api.semanticscholar.org/graph/v1/paper/search?query={quote(query)}&limit=1&fields={fields}'
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code >= 400:
            return {}
        payload = response.json() if response.content else {}
        data = (payload.get('data') or []) if isinstance(payload, dict) else []
        if not data:
            return {}
        item = data[0] or {}
        external = item.get('externalIds') or {}
        return {
            'title': (item.get('title') or '').strip(),
            'authors': _authors_from_semantic(item.get('authors') or []),
            'year': _safe_year(item.get('year')),
            'source': (item.get('venue') or '').strip(),
            'volume': '',
            'issue': '',
            'pages': '',
            'doi': _clean_doi(external.get('DOI')),
            'url': (item.get('url') or '').strip(),
        }
    except Exception:
        return {}


def _metadata_from_crossref_item(item):
    if not isinstance(item, dict):
        return {}
    title_list = item.get('title') or []
    title = title_list[0] if isinstance(title_list, list) and title_list else ''
    container = item.get('container-title') or []
    source = container[0] if isinstance(container, list) and container else ''
    year = _crossref_year(item.get('issued') or {})
    volume = str(item.get('volume') or '').strip()
    issue = str(item.get('issue') or '').strip()
    pages = str(item.get('page') or '').strip()
    doi = _clean_doi(item.get('DOI'))
    url = str(item.get('URL') or '').strip()
    return {
        'title': str(title or '').strip(),
        'authors': _authors_from_crossref(item.get('author') or []),
        'year': _safe_year(year),
        'source': str(source or '').strip(),
        'volume': volume,
        'issue': issue,
        'pages': pages,
        'doi': doi,
        'url': url,
    }


def _merge_metadata(base, override):
    merged = dict(base or {})
    for key, value in (override or {}).items():
        if key == 'authors':
            if value:
                merged[key] = value
            continue
        if value not in (None, ''):
            merged[key] = value
    return merged


def _format_apa_from_metadata(metadata):
    authors = metadata.get('authors') or []
    author_text = _format_authors_apa(authors) if authors else 'Unknown author'
    year_value = metadata.get('year')
    year_text = str(year_value) if year_value else 'n.d.'
    title = (metadata.get('title') or 'Untitled').strip().rstrip('.')
    source = (metadata.get('source') or '').strip()
    volume = (metadata.get('volume') or '').strip()
    issue = (metadata.get('issue') or '').strip()
    pages = (metadata.get('pages') or '').strip()
    doi = _clean_doi(metadata.get('doi'))
    url = (metadata.get('url') or '').strip()

    citation = f'{author_text} ({year_text}). {title}.'

    journal_part = ''
    if source:
        journal_part = f' {source}'
        if volume:
            journal_part += f', {volume}'
            if issue:
                journal_part += f'({issue})'
        if pages:
            journal_part += f', {pages}'
        journal_part += '.'
    citation += journal_part

    if doi:
        citation += f' https://doi.org/{doi}'
    elif url:
        citation += f' {url}'

    return ' '.join(citation.split())


def _normalize_with_deepseek_if_available(*, draft_citation, metadata):
    api_key = getattr(settings, 'DEEPSEEK_API_KEY', '') or os.getenv('DEEPSEEK_API_KEY', '')
    if not api_key:
        return ''

    user_prompt = (
        'Metadata:\n'
        f'{json.dumps(metadata, ensure_ascii=False, indent=2)}\n\n'
        f'Draft citation:\n{draft_citation}\n\n'
        'Return JSON only.'
    )
    try:
        raw = _call_deepseek(system_prompt=DEEPSEEK_APA_NORMALIZER_SYSTEM_PROMPT, user_prompt=user_prompt)
        parsed = _extract_json(raw)
        if not isinstance(parsed, dict):
            return ''
        return str(parsed.get('citation_apa') or '').strip()
    except Exception:
        return ''


def _authors_from_crossref(author_items):
    output = []
    for item in author_items:
        if not isinstance(item, dict):
            continue
        family = (item.get('family') or '').strip()
        given = (item.get('given') or '').strip()
        if not family and not given:
            continue
        output.append({'family': family, 'given': given})
    return output


def _authors_from_semantic(author_items):
    output = []
    for item in author_items:
        if not isinstance(item, dict):
            continue
        name = (item.get('name') or '').strip()
        if not name:
            continue
        family, given = _split_name(name)
        output.append({'family': family, 'given': given})
    return output


def _parse_local_authors(raw):
    parts = [chunk.strip() for chunk in (raw or '').split(';') if chunk.strip()]
    output = []
    for item in parts:
        if ',' in item:
            family, given = [x.strip() for x in item.split(',', 1)]
        else:
            family, given = _split_name(item)
        output.append({'family': family, 'given': given})
    return output


def _split_name(full_name):
    tokens = [t for t in re.split(r'\s+', (full_name or '').strip()) if t]
    if not tokens:
        return '', ''
    if len(tokens) == 1:
        return tokens[0], ''
    return tokens[-1], ' '.join(tokens[:-1])


def _format_authors_apa(authors):
    formatted = []
    for item in authors[:20]:
        family = (item.get('family') or '').strip()
        given = (item.get('given') or '').strip()
        if not family and not given:
            continue
        initials = _to_initials(given)
        if family and initials:
            formatted.append(f'{family}, {initials}')
        elif family:
            formatted.append(family)
        else:
            formatted.append(initials or 'Unknown')

    if not formatted:
        return 'Unknown author'
    if len(formatted) == 1:
        return formatted[0] + '.'
    if len(formatted) == 2:
        return f'{formatted[0]}, & {formatted[1]}.'
    return ', '.join(formatted[:-1]) + f', & {formatted[-1]}.'


def _to_initials(given_names):
    parts = [p for p in re.split(r'[\s\-]+', (given_names or '').strip()) if p]
    initials = []
    for part in parts:
        if part:
            initials.append(part[0].upper() + '.')
    return ' '.join(initials)


def _crossref_year(issued_obj):
    date_parts = (issued_obj or {}).get('date-parts') or []
    if not isinstance(date_parts, list) or not date_parts:
        return None
    first = date_parts[0]
    if not isinstance(first, list) or not first:
        return None
    return _safe_year(first[0])


def _safe_year(value):
    if value in (None, ''):
        return None
    text = str(value).strip()
    match = re.search(r'\d{4}', text)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def _clean_doi(value):
    text = str(value or '').strip()
    if not text:
        return ''
    text = re.sub(r'^https?://(dx\.)?doi\.org/', '', text, flags=re.IGNORECASE).strip()
    text = text.replace('doi:', '').strip()
    return text


def _call_deepseek(*, system_prompt, user_prompt):
    api_key = getattr(settings, 'DEEPSEEK_API_KEY', '') or os.getenv('DEEPSEEK_API_KEY', '')
    if not api_key:
        raise RuntimeError('DEEPSEEK_API_KEY is not configured.')

    base_url = (getattr(settings, 'DEEPSEEK_BASE_URL', '') or os.getenv('DEEPSEEK_BASE_URL', '') or 'https://api.deepseek.com').rstrip('/')
    model_name = getattr(settings, 'DEEPSEEK_LR_CITATION_MODEL', '') or os.getenv('DEEPSEEK_LR_CITATION_MODEL', '') or 'deepseek-chat'
    timeout_seconds = float(getattr(settings, 'DEEPSEEK_TIMEOUT_SECONDS', 90))

    response = requests.post(
        f'{base_url}/chat/completions',
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json={
            'model': model_name,
            'temperature': 0.0,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
        },
        timeout=timeout_seconds,
    )
    if response.status_code >= 400:
        raise RuntimeError(f'DeepSeek HTTP {response.status_code}: {response.text[:1200]}')

    payload = response.json()
    choices = payload.get('choices') or []
    if not choices:
        raise RuntimeError('DeepSeek response missing choices.')

    message = choices[0].get('message') or {}
    content = message.get('content')
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get('type') == 'text':
                parts.append(part.get('text') or '')
            elif isinstance(part, str):
                parts.append(part)
        content = '\n'.join(parts)

    text = (content or '').strip()
    if not text:
        raise RuntimeError('DeepSeek returned empty citation response.')
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
        for idx, char in enumerate(text):
            if char not in '[{':
                continue
            try:
                parsed, _ = decoder.raw_decode(text[idx:])
                return parsed
            except JSONDecodeError:
                continue
    raise RuntimeError('Citation response is not valid JSON.')


def _emit(callback, payload):
    if not callback:
        return
    try:
        callback(payload)
    except Exception:
        return
