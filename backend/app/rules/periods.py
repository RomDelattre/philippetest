"""Périodes : toujours start_date + end_date incluses (P4, R-03)."""

from datetime import date


def overlaps(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    return a_start <= b_end and b_start <= a_end
