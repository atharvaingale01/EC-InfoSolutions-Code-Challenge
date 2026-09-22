"""
Seed demo users, a staff account and two weeks of activity so every endpoint
returns data straight after `make up`.

    python manage.py seed_demo [--no-refresh] [--flush]
"""

import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.activity.models import UserActivity
from apps.core.seed_data import (
    ACTION_WEIGHTS,
    DEMO_PASSWORD,
    DEMO_STAFF,
    DEMO_TRACKS,
    DEMO_USERS,
)

User = get_user_model()
ACTIVITIES_PER_USER = 10
SEED_EMAILS = [u["email"] for u in DEMO_USERS] + [DEMO_STAFF["email"]]


class Command(BaseCommand):
    help = "Create 5 demo users, a staff user and sample activity."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-refresh",
            action="store_true",
            help="Do not enqueue Spotify recommendation refreshes (no Spotify creds needed).",
        )
        parser.add_argument(
            "--flush", action="store_true", help="Delete previously seeded users first."
        )

    @transaction.atomic
    def handle(self, *args, **options):
        rng = random.Random(42)

        if options["flush"]:
            deleted, _ = User.objects.filter(email__in=SEED_EMAILS).delete()
            self.stdout.write(f"Flushed {deleted} seeded rows.")

        created_users = []
        for spec in DEMO_USERS:
            user, created = self._get_or_create(spec)
            created_users.append(user)
            self.stdout.write(f"{'created' if created else 'exists '}  {user.email}")

        staff, created = self._get_or_create(DEMO_STAFF)
        self.stdout.write(f"{'created' if created else 'exists '}  {staff.email} (staff)")

        activity_count = 0
        if not UserActivity.objects.filter(user__in=created_users).exists():
            activity_count = self._seed_activity(created_users, rng)
        self.stdout.write(f"Activity rows created: {activity_count}")

        if not options["no_refresh"]:
            from apps.recommendations.tasks import enqueue_refresh

            for user in created_users:
                transaction.on_commit(lambda u=user: enqueue_refresh(u))
            self.stdout.write(f"Queued recommendation refresh for {len(created_users)} users.")

        self.stdout.write(self.style.SUCCESS(f"Done. Demo password: {DEMO_PASSWORD}"))
        self.stdout.write(
            self.style.WARNING(
                "Demo accounts use a published password. Remove them (seed_demo --flush) "
                "before exposing this stack beyond your machine."
            )
        )

    @staticmethod
    def _get_or_create(spec):
        email = spec["email"]
        user = User.objects.filter(email=email).first()
        if user:
            return user, False
        fields = {k: v for k, v in spec.items() if k != "email"}
        return User.objects.create_user(email=email, password=DEMO_PASSWORD, **fields), True

    @staticmethod
    def _seed_activity(users, rng) -> int:
        actions = list(ACTION_WEIGHTS)
        weights = list(ACTION_WEIGHTS.values())
        now = timezone.now()
        rows = []
        for index, user in enumerate(users):
            # Each user leans towards "their" two tracks plus a random spread.
            favourites = DEMO_TRACKS[index * 2 : index * 2 + 2] or DEMO_TRACKS[:2]
            for _ in range(ACTIVITIES_PER_USER):
                track = rng.choice(favourites if rng.random() < 0.6 else DEMO_TRACKS)
                action = rng.choices(actions, weights=weights, k=1)[0]
                rows.append(
                    UserActivity(
                        user=user,
                        track_id=track[0],
                        track_name=track[1],
                        artist_name=track[2],
                        action=action,
                    )
                )
        UserActivity.objects.bulk_create(rows)
        for row in rows:
            row.created_at = now - timedelta(days=rng.randint(0, 13), hours=rng.randint(0, 23))
        # auto_now_add overrides created_at during bulk_create; write the spread
        # timestamps back so trends over 1 / 7 / 14 days differ.
        UserActivity.objects.bulk_update(rows, ["created_at"])
        return len(rows)
