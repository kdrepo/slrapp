import os
from functools import lru_cache

from django.conf import settings


def prompt_file_path(filename):
    return os.path.join(getattr(settings, 'BASE_DIR', ''), 'reviews', 'prompts', filename)


@lru_cache(maxsize=128)
def load_prompt_template(filename):
    path = prompt_file_path(filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f'Prompt file not found: {path}')
    with open(path, 'r', encoding='utf-8') as handle:
        return handle.read().strip()


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
