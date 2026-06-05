import os
from functools import lru_cache

from django.conf import settings


def prompt_file_path(filename):
    return os.path.join(getattr(settings, 'BASE_DIR', ''), 'reviews', 'prompts', filename)


def _candidate_prompt_names(filename):
    name = (filename or '').replace('\\', '/').strip().lstrip('/')
    if not name:
        return []
    if name.startswith('prompts_final/'):
        return [name]
    return [f'prompts_final/{name}', name]


@lru_cache(maxsize=128)
def load_prompt_template(filename):
    candidates = _candidate_prompt_names(filename)
    for name in candidates:
        path = prompt_file_path(name)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as handle:
                return handle.read().strip()
    searched = ', '.join(prompt_file_path(name) for name in candidates) or str(filename)
    raise FileNotFoundError(f'Prompt file not found. Searched: {searched}')


def render_prompt_template(filename, context=None, fallback=''):
    context = context or {}
    try:
        template = load_prompt_template(filename)
    except FileNotFoundError:
        template = (fallback or '').strip()

    rendered = template
    for key, value in context.items():
        rendered = rendered.replace('{' + key + '}', str(value))
    return rendered
