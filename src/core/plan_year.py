"""The plan year on sale: next year's plans go on sale when open enrollment opens."""
from datetime import date

# HealthCare.gov and Covered California both open on November 1.
_OPEN_ENROLLMENT_OPENS = (11, 1)


def plan_year_on_sale(on: date) -> int:
    return on.year + 1 if (on.month, on.day) >= _OPEN_ENROLLMENT_OPENS else on.year
