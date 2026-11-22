from app.services.limits import DailyBudget, RateLimiter


def test_rate_limiter_blocks_after_limit_and_recovers():
    limiter = RateLimiter(2, 60.0)
    assert limiter.allow("a", now=0.0)
    assert limiter.allow("a", now=1.0)
    assert not limiter.allow("a", now=2.0)
    assert limiter.allow("a", now=61.0)


def test_rate_limiter_tracks_clients_separately():
    limiter = RateLimiter(1, 60.0)
    assert limiter.allow("a", now=0.0)
    assert limiter.allow("b", now=0.0)
    assert not limiter.allow("a", now=1.0)


def test_daily_budget_resets_on_a_new_day():
    budget = DailyBudget(2)
    assert budget.take("2026-11-21")
    assert budget.take("2026-11-21")
    assert not budget.take("2026-11-21")
    assert budget.take("2026-11-22")
