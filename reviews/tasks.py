try:
    from celery import shared_task
    HAS_CELERY = True
except Exception:  # pragma: no cover
    HAS_CELERY = False

    def shared_task(*args, **kwargs):
        def _decorator(func):
            return func
        return _decorator
