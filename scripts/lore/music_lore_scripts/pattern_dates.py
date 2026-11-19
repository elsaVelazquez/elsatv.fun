#!/usr/bin/env python3
"""
pattern_dates.py — the 0/3/6/9 date rule, as one shared definition.

The rule
--------
Reduce the year, the month, and the day to a single digit each by digit-sum.
A part "counts" when it lands on 0, 3, 6, or 9.

Ones are a special case. A `1` is usually worth 1, but when treating the ones
in a part as 0 is what makes that part land on 0/3/6/9, the zeros are used:

    2026-11-18   year 2026 -> 1+0 = 1   (1 -> 0)            => 0
                 month   11 -> 1+1 = 2   (not 0/3/6/9)
                                  0+0 = 0   (1s -> 0)       => 0
                 day     18 -> 1+8 = 9   (already counts)   => 9

    2026-11-03   day     03 -> 3        (already counts)     => 3

    2026-11-11   day     11 -> 1+1 = 2     0+0 = 0           => 0

So the ones-as-zero form is a FALLBACK, tried per part and only when the plain
form misses. It is never a blanket "every 1 becomes 0" rewrite: that would turn
18 into 8 and lose the 9.

A date matches when all three parts resolve. This is a description of a date
that actually exists — it never changes the date itself. Callers must keep
`release_date` authoritative and treat the pattern as a label.
"""

# A part counts when it reduces to one of these.
VALID = (0, 3, 6, 9)


def digit_sum(n):
    """Reduce a positive integer to a single digit by repeated digit-sum."""
    n = abs(int(n))
    while n > 9:
        n = sum(int(c) for c in str(n))
    return n


def digit_sum_no_ones(n):
    """Digit-sum where every `1` is worth 0, then a lone 1 reads as 0."""
    n = abs(int(n))
    while n > 9:
        n = sum(0 if c == '1' else int(c) for c in str(n))
    return 0 if n == 1 else n


def reduce_part(n):
    """One date part -> (digit, 'as-is' | 'ones' | None).

    Tries the number as written first; only if that misses 0/3/6/9 does it retry
    with the ones treated as zeros.
    """
    plain = digit_sum(n)
    if plain in VALID:
        return plain, 'as-is'
    zeros = digit_sum_no_ones(n)
    if zeros in VALID:
        return zeros, 'ones'
    return plain, None


def signature(iso_date):
    """(month, day, year) reduced digits, plus whether all three resolved.

    Returned in month · day · year order: that is how the vortexes are listed
    on the site, so 2026-11-18 reads 0 · 9 · 0. The parts are still reduced and
    matched by their own values — only the report order changes.

    Returns None for an unparseable/missing date rather than guessing.
    """
    try:
        y, m, d = (int(p) for p in str(iso_date)[:10].split('-'))
    except (ValueError, AttributeError):
        return None
    parts = [reduce_part(m), reduce_part(d), reduce_part(y)]
    return {
        'digits': [p[0] for p in parts],
        'how': [p[1] for p in parts],
        'matches': all(p[1] is not None for p in parts),
    }


def matches(iso_date):
    """True when the date lands on the 0/3/6/9 pattern in all three parts."""
    sig = signature(iso_date)
    return bool(sig and sig['matches'])


def label(iso_date):
    """Compact signature for the site, e.g. '0 · 9 · 3'. Empty when no match."""
    sig = signature(iso_date)
    if not sig or not sig['matches']:
        return ''
    return ' · '.join(str(d) for d in sig['digits'])


def pick(iso_dates):
    """The first candidate that lands on the pattern, else the first given.

    A release carries several real dates, and they need not agree:
    `release_date` is the scheduled go-live day, `created_at` the day it was
    sent to ONCE, `first_distributed_at` the day delivery actually started. A
    release submitted Nov 3 for a Nov 5 go-live is a real Nov 3, so when Nov 5
    misses the pattern and Nov 3 hits it, Nov 3 is the honest answer — it is not
    an invented date, it is one ONCE recorded.

    Order matters: pass the most authoritative first, so a candidate is only
    skipped when it genuinely misses the pattern. A date is never adjusted, only
    chosen from the dates that already exist. With no match anywhere, the first
    candidate wins and callers can tell via `matches()` that it did not land.
    """
    dates = [str(d)[:10] for d in iso_dates if d]
    for d in dates:
        if matches(d):
            return d
    return dates[0] if dates else ''


if __name__ == '__main__':
    import sys

    dates = sys.argv[1:] or ['2026-11-18', '2026-11-03', '2026-11-11',
                             '2026-11-05', '2026-11-17']
    for d in dates:
        sig = signature(d)
        if not sig:
            print(f'{d}  unparseable')
            continue
        mark = label(d) if sig['matches'] else '—'
        print(f"{d}  {sig['digits']}  {sig['how']}  {mark}")

    # A release's dates can disagree; show which one the site would use.
    if len(dates) > 1:
        print(f'\npick({dates}) -> {pick(dates)}')
