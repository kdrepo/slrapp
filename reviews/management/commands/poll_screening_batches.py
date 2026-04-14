import time
from datetime import datetime

from django.core.management.base import BaseCommand

from reviews.services.screening_service import poll_active_screening_batches


class Command(BaseCommand):
    help = 'Poll active Gemini title/abstract screening queues (standard Flash API).'

    def add_arguments(self, parser):
        parser.add_argument('--interval', type=int, default=60, help='Polling interval in seconds (default: 60).')
        parser.add_argument('--loop', action='store_true', help='Keep polling continuously.')
        parser.add_argument('--max-cycles', type=int, default=0, help='Stop after N cycles when --loop is used (0 = unlimited).')

    def handle(self, *args, **options):
        interval = max(1, int(options.get('interval') or 60))
        loop_mode = bool(options.get('loop'))
        max_cycles = max(0, int(options.get('max_cycles') or 0))

        cycle = 0
        while True:
            cycle += 1
            started_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.stdout.write(self.style.NOTICE(f'[{started_at}] Poll cycle {cycle} started'))

            summaries = poll_active_screening_batches()
            if not summaries:
                self.stdout.write(self.style.WARNING('No active screening queues found.'))
            else:
                for item in summaries:
                    review_id = item.get('review_id')
                    stage_key = item.get('stage_key', 'phase_7')
                    state = item.get('state')
                    updated = item.get('updated', 0)
                    conflicts = item.get('conflicts', 0)
                    remaining = item.get('remaining', 'n/a')
                    error = item.get('error')
                    if error:
                        self.stdout.write(self.style.ERROR(f'Review {review_id} [{stage_key}]: {error}'))
                    else:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'Review {review_id} [{stage_key}]: state={state}, updated={updated}, conflicts={conflicts}, remaining={remaining}'
                            )
                        )

            if not loop_mode:
                break

            if max_cycles and cycle >= max_cycles:
                self.stdout.write(self.style.WARNING(f'Max cycles reached ({max_cycles}). Stopping.'))
                break

            self.stdout.write(self.style.NOTICE(f'Next poll in {interval} seconds...'))
            time.sleep(interval)
