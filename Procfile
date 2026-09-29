web: daphne -b 0.0.0.0 -p $PORT technicians.asgi:application
worker: celery -A technicians worker --beat --loglevel=info --concurrency=1 --scheduler django_celery_beat.schedulers:DatabaseScheduler