import json
import os
import re
import time
from urllib.parse import quote

import requests
from django.conf import settings

from reviews.models import Paper, Review


def enrich_missing_abstracts_from_scopus(
    review_id,
    title_screening_decisions,
    progress_callback=None,
    stop_check=None,
):
    review = Review.objects.get(pk=review_id)
    selected = _normalize_decisions(title_screening_decisions)

    papers = list(
        review.papers.filter(title_screening_decision__in=selected).filter(abstract__isnull=True)
        | review.papers.filter(title_screening_decision__in=selected).filter(abstract='')
    )
    papers = sorted({paper.id: paper for paper in papers}.values(), key=lambda p: p.id)

    summary = {
        'review_id': review.id,
        'selected_decisions': selected,
        'targeted': len(papers),
        'updated': 0,
        'abstract_filled': 0,
        'failed': 0,
        'rows': [],
        'stopped': False,
    }

    _emit(
        progress_callback,
        {
            'event': 'started',
            'review_id': review.id,
            'targeted': len(papers),
            'selected_decisions': selected,
        },
    )

    for index, paper in enumerate(papers, start=1):
        if stop_check and stop_check():
            summary['stopped'] = True
            _emit(
                progress_callback,
                {
                    'event': 'stopped',
                    'paper_id': paper.id,
                    'message': 'Stop requested by user.',
                },
            )
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

        before_abstract = (paper.abstract or '').strip()
        fetch = _fetch_metadata_for_paper(paper)

        if not fetch.get('ok'):
            summary['failed'] += 1
            row = {
                'paper_id': paper.id,
                'status': 'failed',
                'message': fetch.get('error') or 'Metadata lookup failed.',
                'source': fetch.get('source') or '',
                'status_code': fetch.get('status_code'),
            }
            summary['rows'].append(row)
            _emit(
                progress_callback,
                {
                    'event': 'failed',
                    'paper_id': paper.id,
                    'title': paper.title,
                    'status_code': row['status_code'],
                    'source': row['source'],
                    'message': row['message'],
                },
            )
            continue

        updates = _apply_updates_to_paper(paper, fetch.get('updates') or {})
        if updates:
            paper.save(update_fields=updates)
            summary['updated'] += 1
            after_abstract = (paper.abstract or '').strip()
            if not before_abstract and after_abstract:
                summary['abstract_filled'] += 1

            row = {
                'paper_id': paper.id,
                'status': 'updated',
                'message': f'Updated fields: {", ".join(updates)}',
                'source': fetch.get('source') or '',
                'status_code': fetch.get('status_code'),
            }
            summary['rows'].append(row)
            _emit(
                progress_callback,
                {
                    'event': 'updated',
                    'paper_id': paper.id,
                    'title': paper.title,
                    'status_code': row['status_code'],
                    'source': row['source'],
                    'message': row['message'],
                },
            )
        else:
            row = {
                'paper_id': paper.id,
                'status': 'no_change',
                'message': fetch.get('message') or 'No newer metadata found for this paper.',
                'source': fetch.get('source') or '',
                'status_code': fetch.get('status_code'),
            }
            summary['rows'].append(row)
            _emit(
                progress_callback,
                {
                    'event': 'no_change',
                    'paper_id': paper.id,
                    'title': paper.title,
                    'status_code': row['status_code'],
                    'source': row['source'],
                    'message': row['message'],
                },
            )

        time.sleep(float(getattr(settings, 'PDF_RETRIEVAL_DELAY_SECONDS', 1.0) or 1.0))

    _emit(progress_callback, {'event': 'completed', **summary})
    return summary


def probe_scopus_metadata_for_paper(paper):
    return _fetch_metadata_for_paper(paper)


def _normalize_decisions(values):
    allowed = {
        Paper.TitleScreeningDecision.INCLUDED,
        Paper.TitleScreeningDecision.EXCLUDED,
        Paper.TitleScreeningDecision.UNCERTAIN,
        Paper.TitleScreeningDecision.MANUAL_TITLES,
        Paper.TitleScreeningDecision.NOT_PROCESSED,
    }
    normalized = []
    for item in values or []:
        value = str(item or '').strip().lower()
        if value in allowed and value not in normalized:
            normalized.append(value)
    return normalized or list(allowed)


def _fetch_metadata_for_paper(paper):
    attempts = []
    best_no_abstract = None
    title = (paper.title or '').strip()
    doi = (paper.doi or '').strip()

    for fetcher in (
        lambda: _fetch_from_elsevier(paper),
        lambda: _fetch_from_crossref(doi),
        lambda: _fetch_from_openalex(doi, title),
        lambda: _fetch_from_semantic_scholar(doi, title),
        lambda: _fetch_from_europe_pmc(doi, title),
    ):
        result = fetcher()
        attempts.append(result)

        if not result.get('ok'):
            continue
        if result.get('has_abstract'):
            return result
        if best_no_abstract is None:
            best_no_abstract = result

    if best_no_abstract:
        best_no_abstract['message'] = (
            'Metadata found, but no abstract was available from fallback sources.'
        )
        return best_no_abstract

    failed = [a for a in attempts if not a.get('ok')]
    tail = failed[-2:] if failed else []
    details = ' | '.join(
        f"{item.get('source', 'unknown')}: {item.get('error', 'failed')}"
        for item in tail
    ) or 'All metadata sources failed.'
    return {
        'ok': False,
        'source': (tail[-1].get('source') if tail else 'metadata_fallbacks'),
        'status_code': (tail[-1].get('status_code') if tail else None),
        'error': details,
    }


def _fetch_from_elsevier(paper):
    if not (getattr(settings, 'ELSEVIER_API_KEY', '') or '').strip():
        return {
            'ok': False,
            'source': 'elsevier',
            'status_code': None,
            'error': 'ELSEVIER_API_KEY is missing.',
        }

    doi = (paper.doi or '').strip()
    if doi:
        result = _call_elsevier_abstract_by_doi(doi)
        if result.get('ok'):
            return result

    eid = _normalize_eid(paper.scopus_id)
    if eid:
        result = _call_elsevier_abstract_by_eid(eid)
        if result.get('ok'):
            return result

    search = _search_scopus_by_title(paper.title)
    if not search.get('ok'):
        return {
            'ok': False,
            'source': 'elsevier_title_search',
            'status_code': search.get('status_code'),
            'error': search.get('error') or 'Scopus title search failed.',
        }

    entry = search.get('entry') or {}
    candidate_doi = (entry.get('prism:doi') or '').strip()
    candidate_eid = _normalize_eid(entry.get('eid') or '')

    if candidate_doi:
        result = _call_elsevier_abstract_by_doi(candidate_doi)
        if result.get('ok'):
            return result
    if candidate_eid:
        result = _call_elsevier_abstract_by_eid(candidate_eid)
        if result.get('ok'):
            return result

    return {
        'ok': False,
        'source': 'elsevier',
        'status_code': search.get('status_code'),
        'error': 'No metadata record could be resolved from DOI/EID/title search.',
    }


def _call_elsevier_abstract_by_doi(doi):
    api_url = f'https://api.elsevier.com/content/abstract/doi/{quote(doi, safe="")}'
    response = _get_json(
        api_url,
        headers=_elsevier_headers(),
        params={'view': 'FULL'},
        timeout=30,
    )
    if not response.get('ok'):
        return {
            'ok': False,
            'source': 'elsevier_abstract_by_doi',
            'status_code': response.get('status_code'),
            'error': response.get('error'),
        }
    payload = (response.get('payload') or {}).get('abstracts-retrieval-response') or {}
    updates = _extract_elsevier_updates(payload)
    return {
        'ok': True,
        'source': 'elsevier_abstract_by_doi',
        'status_code': response.get('status_code'),
        'updates': updates,
        'has_abstract': bool((updates.get('abstract') or '').strip()),
    }


def _call_elsevier_abstract_by_eid(eid):
    api_url = f'https://api.elsevier.com/content/abstract/eid/{quote(eid, safe="")}'
    response = _get_json(
        api_url,
        headers=_elsevier_headers(),
        params={'view': 'FULL'},
        timeout=30,
    )
    if not response.get('ok'):
        return {
            'ok': False,
            'source': 'elsevier_abstract_by_eid',
            'status_code': response.get('status_code'),
            'error': response.get('error'),
        }
    payload = (response.get('payload') or {}).get('abstracts-retrieval-response') or {}
    updates = _extract_elsevier_updates(payload)
    return {
        'ok': True,
        'source': 'elsevier_abstract_by_eid',
        'status_code': response.get('status_code'),
        'updates': updates,
        'has_abstract': bool((updates.get('abstract') or '').strip()),
    }


def _search_scopus_by_title(title):
    if not (title or '').strip():
        return {'ok': False, 'error': 'Title is empty.', 'status_code': None}

    response = _get_json(
        'https://api.elsevier.com/content/search/scopus',
        headers=_elsevier_headers(),
        params={
            'query': f'TITLE("{title}")',
            'count': 1,
            'view': 'COMPLETE',
        },
        timeout=30,
    )
    if not response.get('ok'):
        return {
            'ok': False,
            'error': response.get('error') or 'Scopus title search failed.',
            'status_code': response.get('status_code'),
        }
    entries = (((response.get('payload') or {}).get('search-results') or {}).get('entry') or [])
    if not entries:
        return {
            'ok': False,
            'error': 'No Scopus search result found for title.',
            'status_code': response.get('status_code'),
        }
    entry = entries[0] if isinstance(entries, list) else entries
    return {'ok': True, 'entry': entry, 'status_code': response.get('status_code')}


def _extract_elsevier_updates(payload):
    core = payload.get('coredata') or {}
    authors_blob = (payload.get('authors') or {}).get('author') or []
    keywords_blob = (payload.get('authkeywords') or {}).get('author-keyword') or []
    return {
        'title': (core.get('dc:title') or '').strip(),
        'abstract': (core.get('dc:description') or '').strip(),
        'doi': (core.get('prism:doi') or '').strip(),
        'scopus_id': _normalize_eid(core.get('eid') or ''),
        'journal': (core.get('prism:publicationName') or '').strip(),
        'volume': (core.get('prism:volume') or '').strip(),
        'number': (core.get('prism:issueIdentifier') or '').strip(),
        'start_page': (core.get('prism:startingPage') or '').strip(),
        'end_page': (core.get('prism:endingPage') or '').strip(),
        'publisher': (core.get('dc:publisher') or '').strip(),
        'issn': (core.get('prism:issn') or '').strip(),
        'url': (core.get('prism:url') or '').strip(),
        'citation_count': _safe_int(core.get('citedby-count')),
        'publication_year': _extract_year(core.get('prism:coverDate') or ''),
        'language': _extract_language(payload.get('language')),
        'type_of_work': (core.get('subtypeDescription') or core.get('srctype') or '').strip(),
        'authors': _extract_authors(authors_blob),
        'keywords': _extract_keywords(keywords_blob),
    }


def _fetch_from_crossref(doi):
    if not doi:
        return {'ok': False, 'source': 'crossref', 'status_code': None, 'error': 'DOI missing.'}

    response = _get_json(
        f'https://api.crossref.org/works/{quote(doi, safe="")}',
        headers={'Accept': 'application/json'},
        timeout=30,
    )
    if not response.get('ok'):
        return {
            'ok': False,
            'source': 'crossref',
            'status_code': response.get('status_code'),
            'error': response.get('error'),
        }

    message = ((response.get('payload') or {}).get('message') or {})
    updates = {
        'title': _first_str(message.get('title')),
        'abstract': _strip_markup(message.get('abstract') or ''),
        'doi': (message.get('DOI') or '').strip(),
        'journal': _first_str(message.get('container-title')),
        'volume': str(message.get('volume') or '').strip(),
        'number': str(message.get('issue') or '').strip(),
        'publisher': str(message.get('publisher') or '').strip(),
        'issn': ' '.join(message.get('ISSN') or []),
        'url': str(message.get('URL') or '').strip(),
        'publication_year': _extract_year_from_crossref(message),
        'authors': _extract_crossref_authors(message.get('author') or []),
        'keywords': '; '.join([str(s).strip() for s in (message.get('subject') or []) if str(s).strip()]),
        'type_of_work': str(message.get('type') or '').strip(),
    }
    start_page, end_page = _split_pages(str(message.get('page') or ''))
    updates['start_page'] = start_page
    updates['end_page'] = end_page
    return {
        'ok': True,
        'source': 'crossref',
        'status_code': response.get('status_code'),
        'updates': updates,
        'has_abstract': bool((updates.get('abstract') or '').strip()),
    }


def _fetch_from_openalex(doi, title):
    headers = {'Accept': 'application/json'}
    response = None

    if doi:
        response = _get_json(
            f'https://api.openalex.org/works/https://doi.org/{quote(doi, safe="")}',
            headers=headers,
            timeout=30,
        )
    if not response or not response.get('ok'):
        if not title:
            return {
                'ok': False,
                'source': 'openalex',
                'status_code': (response.get('status_code') if response else None),
                'error': (response.get('error') if response else 'No DOI/title for OpenAlex lookup.'),
            }
        response = _get_json(
            'https://api.openalex.org/works',
            headers=headers,
            params={'search': title, 'per-page': 1},
            timeout=30,
        )
        if not response.get('ok'):
            return {
                'ok': False,
                'source': 'openalex',
                'status_code': response.get('status_code'),
                'error': response.get('error'),
            }
        works = response.get('payload', {}).get('results') or []
        if not works:
            return {'ok': False, 'source': 'openalex', 'status_code': response.get('status_code'), 'error': 'No OpenAlex result.'}
        record = works[0]
    else:
        record = response.get('payload') or {}

    abstract = _rebuild_openalex_abstract(record.get('abstract_inverted_index') or {})
    source = ((record.get('primary_location') or {}).get('source') or {})
    biblio = record.get('biblio') or {}
    doi_url = str(record.get('doi') or '').strip()

    updates = {
        'title': str(record.get('title') or '').strip(),
        'abstract': abstract,
        'doi': _normalize_doi_url(doi_url),
        'journal': str(source.get('display_name') or '').strip(),
        'volume': str(biblio.get('volume') or '').strip(),
        'number': str(biblio.get('issue') or '').strip(),
        'start_page': str(biblio.get('first_page') or '').strip(),
        'end_page': str(biblio.get('last_page') or '').strip(),
        'issn': str(source.get('issn_l') or '').strip(),
        'url': str((record.get('primary_location') or {}).get('landing_page_url') or record.get('id') or '').strip(),
        'publication_year': _safe_int(record.get('publication_year')),
        'citation_count': _safe_int(record.get('cited_by_count')),
        'language': str(record.get('language') or '').strip(),
        'authors': _extract_openalex_authors(record.get('authorships') or []),
        'keywords': _extract_openalex_keywords(record.get('concepts') or []),
        'type_of_work': str(record.get('type') or '').strip(),
    }
    return {
        'ok': True,
        'source': 'openalex',
        'status_code': response.get('status_code'),
        'updates': updates,
        'has_abstract': bool((abstract or '').strip()),
    }


def _fetch_from_semantic_scholar(doi, title):
    api_key = getattr(settings, 'S2_API_KEY', '') or os.getenv('S2_API_KEY', '')
    headers = {'Accept': 'application/json'}
    if api_key:
        headers['x-api-key'] = api_key

    fields = 'title,abstract,year,venue,externalIds,url,citationCount,authors,fieldsOfStudy'
    response = None
    record = None
    if doi:
        response = _get_json(
            f'https://api.semanticscholar.org/graph/v1/paper/DOI:{quote(doi, safe="")}',
            headers=headers,
            params={'fields': fields},
            timeout=30,
        )
        if response.get('ok'):
            record = response.get('payload') or {}
    if record is None and title:
        response = _get_json(
            'https://api.semanticscholar.org/graph/v1/paper/search',
            headers=headers,
            params={'query': title, 'limit': 1, 'fields': fields},
            timeout=30,
        )
        if not response.get('ok'):
            return {
                'ok': False,
                'source': 'semantic_scholar',
                'status_code': response.get('status_code'),
                'error': response.get('error'),
            }
        data = response.get('payload', {}).get('data') or []
        if not data:
            return {'ok': False, 'source': 'semantic_scholar', 'status_code': response.get('status_code'), 'error': 'No Semantic Scholar result.'}
        record = data[0]

    if record is None:
        return {
            'ok': False,
            'source': 'semantic_scholar',
            'status_code': (response.get('status_code') if response else None),
            'error': 'No DOI/title for Semantic Scholar lookup.',
        }

    ext = record.get('externalIds') or {}
    updates = {
        'title': str(record.get('title') or '').strip(),
        'abstract': str(record.get('abstract') or '').strip(),
        'doi': str(ext.get('DOI') or '').strip(),
        'journal': str(record.get('venue') or '').strip(),
        'url': str(record.get('url') or '').strip(),
        'publication_year': _safe_int(record.get('year')),
        'citation_count': _safe_int(record.get('citationCount')),
        'authors': '; '.join([str((a or {}).get('name') or '').strip() for a in (record.get('authors') or []) if str((a or {}).get('name') or '').strip()]),
        'keywords': '; '.join([str(k).strip() for k in (record.get('fieldsOfStudy') or []) if str(k).strip()]),
    }
    return {
        'ok': True,
        'source': 'semantic_scholar',
        'status_code': (response.get('status_code') if response else 200),
        'updates': updates,
        'has_abstract': bool((updates.get('abstract') or '').strip()),
    }


def _fetch_from_europe_pmc(doi, title):
    query = ''
    if doi:
        query = f'DOI:"{doi}"'
    elif title:
        query = f'TITLE:"{title}"'
    else:
        return {'ok': False, 'source': 'europe_pmc', 'status_code': None, 'error': 'No DOI/title for Europe PMC lookup.'}

    response = _get_json(
        'https://www.ebi.ac.uk/europepmc/webservices/rest/search',
        headers={'Accept': 'application/json'},
        params={'query': query, 'format': 'json', 'pageSize': 1},
        timeout=30,
    )
    if not response.get('ok'):
        return {
            'ok': False,
            'source': 'europe_pmc',
            'status_code': response.get('status_code'),
            'error': response.get('error'),
        }
    results = (((response.get('payload') or {}).get('resultList') or {}).get('result') or [])
    if not results:
        return {'ok': False, 'source': 'europe_pmc', 'status_code': response.get('status_code'), 'error': 'No Europe PMC result.'}
    record = results[0]
    authors = str(record.get('authorString') or '').strip()
    updates = {
        'title': str(record.get('title') or '').strip(),
        'abstract': str(record.get('abstractText') or '').strip(),
        'doi': str(record.get('doi') or '').strip(),
        'journal': str(record.get('journalTitle') or '').strip(),
        'publication_year': _safe_int(record.get('pubYear')),
        'citation_count': _safe_int(record.get('citedByCount')),
        'authors': authors,
        'type_of_work': str(record.get('pubType') or '').strip(),
        'url': str(record.get('source') or '').strip(),
    }
    return {
        'ok': True,
        'source': 'europe_pmc',
        'status_code': response.get('status_code'),
        'updates': updates,
        'has_abstract': bool((updates.get('abstract') or '').strip()),
    }


def _apply_updates_to_paper(paper, updates):
    allowed_fields = {
        'title', 'authors', 'abstract', 'publication_year', 'journal',
        'volume', 'number', 'start_page', 'end_page', 'publisher',
        'issn', 'language', 'type_of_work', 'doi', 'scopus_id',
        'url', 'keywords', 'citation_count',
    }
    changed = []
    for field, value in (updates or {}).items():
        if field not in allowed_fields:
            continue
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue

        current = getattr(paper, field)
        if current != value:
            setattr(paper, field, value)
            changed.append(field)
    return changed


def _elsevier_headers():
    return {
        'X-ELS-APIKey': (getattr(settings, 'ELSEVIER_API_KEY', '') or '').strip(),
        'X-ELS-Insttoken': (getattr(settings, 'ELSEVIER_INSTTOKEN', '') or '').strip(),
        'Accept': 'application/json',
    }


def _get_json(url, headers=None, params=None, timeout=30):
    try:
        response = requests.get(url, headers=headers or {}, params=params or {}, timeout=timeout)
    except requests.RequestException as exc:
        return {'ok': False, 'status_code': None, 'error': f'Network error: {exc}'}

    if response.status_code >= 400:
        return {'ok': False, 'status_code': response.status_code, 'error': f'HTTP {response.status_code}: {response.text[:400]}'}

    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        return {'ok': False, 'status_code': response.status_code, 'error': f'Invalid JSON: {exc}'}

    return {'ok': True, 'status_code': response.status_code, 'payload': payload}


def _normalize_eid(value):
    text = str(value or '').strip()
    if not text:
        return ''
    if text.startswith('2-s2.0-'):
        return text
    if text.isdigit():
        return f'2-s2.0-{text}'
    return text


def _normalize_doi_url(value):
    text = str(value or '').strip()
    if not text:
        return ''
    prefix = 'https://doi.org/'
    if text.lower().startswith(prefix):
        return text[len(prefix):].strip()
    return text


def _extract_year(text):
    value = str(text or '').strip()
    if not value:
        return None
    match = re.search(r'(19|20)\d{2}', value)
    if not match:
        return None
    return _safe_int(match.group(0))


def _extract_language(language_node):
    if isinstance(language_node, dict):
        return str(language_node.get('@xml:lang') or language_node.get('$') or '').strip()
    if isinstance(language_node, str):
        return language_node.strip()
    return ''


def _extract_authors(authors_blob):
    if isinstance(authors_blob, dict):
        authors_blob = [authors_blob]
    names = []
    for author in authors_blob or []:
        if not isinstance(author, dict):
            continue
        preferred = author.get('preferred-name') or {}
        indexed = preferred.get('ce:indexed-name') if isinstance(preferred, dict) else ''
        if indexed:
            names.append(str(indexed).strip())
            continue
        given = author.get('ce:given-name') or ''
        surname = author.get('ce:surname') or ''
        full = f'{given} {surname}'.strip()
        if full:
            names.append(full)
    return '; '.join([n for n in names if n])


def _extract_keywords(keywords_blob):
    if isinstance(keywords_blob, dict):
        keywords_blob = [keywords_blob]
    keywords = []
    for item in keywords_blob or []:
        value = str(item.get('$') if isinstance(item, dict) else item or '').strip()
        if value:
            keywords.append(value)
    return '; '.join(keywords)


def _strip_markup(text):
    value = str(text or '').strip()
    if not value:
        return ''
    value = re.sub(r'<[^>]+>', ' ', value)
    value = re.sub(r'\s+', ' ', value).strip()
    return value


def _first_str(value):
    if isinstance(value, list):
        return str(value[0] or '').strip() if value else ''
    return str(value or '').strip()


def _extract_year_from_crossref(message):
    for key in ('issued', 'published-print', 'published-online', 'created'):
        node = message.get(key) or {}
        parts = node.get('date-parts') or []
        if parts and isinstance(parts[0], list) and parts[0]:
            year = _safe_int(parts[0][0])
            if year:
                return year
    return None


def _extract_crossref_authors(authors):
    names = []
    for author in authors or []:
        if not isinstance(author, dict):
            continue
        family = str(author.get('family') or '').strip()
        given = str(author.get('given') or '').strip()
        full = f'{given} {family}'.strip()
        if full:
            names.append(full)
    return '; '.join(names)


def _split_pages(page_text):
    text = str(page_text or '').strip()
    if not text:
        return '', ''
    if '-' in text:
        first, last = text.split('-', 1)
        return first.strip(), last.strip()
    return text, ''


def _rebuild_openalex_abstract(index_map):
    if not isinstance(index_map, dict) or not index_map:
        return ''
    tokens = []
    for word, positions in index_map.items():
        for pos in positions or []:
            if isinstance(pos, int):
                tokens.append((pos, word))
    if not tokens:
        return ''
    tokens.sort(key=lambda item: item[0])
    return ' '.join([token for _, token in tokens]).strip()


def _extract_openalex_authors(authorships):
    names = []
    for item in authorships or []:
        author = (item or {}).get('author') or {}
        name = str(author.get('display_name') or '').strip()
        if name:
            names.append(name)
    return '; '.join(names)


def _extract_openalex_keywords(concepts):
    keywords = []
    for concept in concepts or []:
        name = str((concept or {}).get('display_name') or '').strip()
        score = concept.get('score')
        if name and (score is None or float(score) >= 0.5):
            keywords.append(name)
        if len(keywords) >= 8:
            break
    return '; '.join(keywords)


def _safe_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _emit(callback, payload):
    if not callback:
        return
    try:
        callback(payload)
    except Exception:
        return
