import signal
import time

from django.core.management.base import BaseCommand

from webhooks.delivery import deliver_due

IDLE_SLEEP_SECONDS = 1


class Command(BaseCommand):
    help = 'Deliver pending outbound webhooks (polls the outbox table).'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Process due deliveries once and exit.')

    def handle(self, *args, once=False, **options):
        if once:
            n = deliver_due()
            self.stdout.write(f'Attempted {n} deliveries.')
            return

        self._stopping = False
        signal.signal(signal.SIGTERM, self._stop)
        signal.signal(signal.SIGINT, self._stop)
        self.stdout.write('Webhook worker started.')
        while not self._stopping:
            n = deliver_due()
            if n:
                self.stdout.write(f'Attempted {n} deliveries.')
            else:
                time.sleep(IDLE_SLEEP_SECONDS)
        self.stdout.write('Webhook worker stopped.')

    def _stop(self, *_):
        self._stopping = True
