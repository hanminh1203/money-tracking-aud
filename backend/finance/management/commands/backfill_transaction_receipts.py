"""Backfill one-line receipts for transactions that do not have one.

Writes the Google Sheet first, then Postgres, for one user. Tokens stay in the
environment so they are not stored in shell history as command arguments.

Examples:

    python manage.py backfill_transaction_receipts --dry-run --user-email you@example.com
    GOOGLE_ACCESS_TOKEN=... python manage.py backfill_transaction_receipts --user-email you@example.com
"""

from __future__ import annotations

import json
import os

from django.core.management.base import BaseCommand, CommandError

from finance.models import User
from finance.receipt_backfill import BackfillWriteError, backfill_missing_receipts
from finance.sheets_client import SheetsClient, SheetsError


class Command(BaseCommand):
    help = (
        'Create a single receipt line for transactions that have none, '
        'on the Google Sheet and in Postgres.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Count rows that would change without writing the sheet or the database.',
        )
        parser.add_argument(
            '--user-email',
            default='',
            help='Account to update. Required when more than one user exists.',
        )

    def handle(self, *args, **options):
        email = str(options['user_email'] or '').strip()
        users = User.objects.all()
        if email:
            users = users.filter(email__iexact=email)
        matched = list(users)
        if not matched:
            raise CommandError('No matching user.')
        if len(matched) > 1:
            raise CommandError('Pass --user-email; more than one user exists.')
        user = matched[0]
        if not (user.sheet_id or '').strip():
            raise CommandError(
                f'{user.email} has no sheet ID. Set it under Management, then run this again.'
            )

        token = str(os.environ.get('GOOGLE_ACCESS_TOKEN') or '').strip()
        if not token:
            raise CommandError(
                'Set GOOGLE_ACCESS_TOKEN in the environment. '
                'Do not pass the token as a command argument. '
                'On the hosted app, Management → Backfill receipt lines uses the signed-in session instead.'
            )

        client = SheetsClient(token, user.sheet_id, user=user)
        try:
            summary = backfill_missing_receipts(
                user=user,
                client=client,
                dry_run=bool(options['dry_run']),
            )
        except SheetsError as exc:
            raise CommandError(str(exc)) from exc
        except BackfillWriteError as exc:
            self.stdout.write(json.dumps(exc.summary, indent=2, default=str))
            raise CommandError(str(exc)) from exc

        self.stdout.write(json.dumps(summary, indent=2, default=str))
