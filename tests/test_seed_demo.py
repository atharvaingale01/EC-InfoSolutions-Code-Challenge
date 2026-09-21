import pytest
from django.core.management import call_command

from apps.activity.models import UserActivity
from apps.core.seed_data import DEMO_USERS
from apps.recommendations.models import Recommendation
from apps.users.models import User


@pytest.mark.django_db(transaction=True)
def test_seed_demo_is_idempotent():
    call_command("seed_demo", verbosity=0)
    assert User.objects.filter(is_staff=False).count() == len(DEMO_USERS)
    assert User.objects.filter(email="admin@example.com", is_staff=True).exists()
    assert UserActivity.objects.count() == 50
    # eager celery: refresh already ran via on_commit
    assert Recommendation.objects.filter(status="ready").count() == len(DEMO_USERS)

    call_command("seed_demo", verbosity=0)
    assert User.objects.count() == len(DEMO_USERS) + 1
    assert UserActivity.objects.count() == 50


@pytest.mark.django_db(transaction=True)
def test_seed_demo_no_refresh_and_flush():
    call_command("seed_demo", "--no-refresh", verbosity=0)
    assert Recommendation.objects.count() == 0
    call_command("seed_demo", "--flush", "--no-refresh", verbosity=0)
    assert User.objects.count() == len(DEMO_USERS) + 1
    assert UserActivity.objects.count() == 50
