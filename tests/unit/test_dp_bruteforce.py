"""AK-4: the daily DP equals a full enumeration for small cases."""

from __future__ import annotations

import itertools
import math
from dataclasses import replace

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from custom_components.netzentgelt_rechner.calc import Params, dp_day


def brute(cb, fi, imp, exp, cap, p: Params) -> float:
    q = p.step
    n = int(cap / q)
    eta = math.sqrt(p.eta_rt)
    pmax = p.c_rate * cap
    kc = max(1, int(pmax * eta / q))
    kd = max(1, int(pmax / (eta * q)))
    best = 0.0
    for ks in itertools.product(range(-kd, kc + 1), repeat=len(cb)):
        e = 0
        c = 0.0
        ok = True
        for h, k in enumerate(ks):
            e += k
            if e < 0 or e > n:
                ok = False
                break
            if k > 0:
                bus = k * q / eta
                ab = min(exp[h], bus)
                if p.grid_import_kw and bus - ab > max(0.0, p.grid_import_kw - imp[h]) + 1e-12:
                    ok = False
                    break
                c += (bus - ab) * cb[h] + ab * fi[h] + p.wear * k * q
            elif k < 0:
                d = -k * q * eta
                use = min(d, imp[h])
                if p.grid_export_kw and d - use > max(0.0, p.grid_export_kw - exp[h]) + 1e-12:
                    ok = False
                    break
                c += -use * cb[h] - (d - use) * fi[h] + p.wear * (-k) * q
        if ok and c < best:
            best = c
    return best


HOURS = 4
prices = st.lists(st.floats(0.0, 0.6), min_size=HOURS, max_size=HOURS)
energy = st.lists(st.floats(0.0, 2.0), min_size=HOURS, max_size=HOURS)
feed = st.lists(st.sampled_from([0.0, 0.0629]), min_size=HOURS, max_size=HOURS)


@settings(
    max_examples=1000,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(
    cb=prices,
    fi=feed,
    imp=energy,
    exp=energy,
    cap=st.sampled_from([2.0, 3.0]),
    wear=st.sampled_from([0.0, 0.01]),
)
def test_dp_equals_bruteforce(params, cb, fi, imp, exp, cap, wear):  # AK-4
    p = replace(params, c_rate=1.0, wear=wear)
    assert abs(dp_day(cb, fi, imp, exp, cap, p) - brute(cb, fi, imp, exp, cap, p)) < 1e-9


@settings(
    max_examples=1000,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(
    cb=prices,
    fi=feed,
    imp=energy,
    exp=energy,
    cap=st.sampled_from([2.0, 3.0]),
    grid_import=st.sampled_from([0.0, 0.5, 1.0, 2.5]),
    grid_export=st.sampled_from([0.0, 0.5, 1.0, 2.5]),
)
def test_dp_with_grid_limits_equals_bruteforce(  # AK-4, AK-19
    params, cb, fi, imp, exp, cap, grid_import, grid_export
):
    p = replace(params, c_rate=1.0, grid_import_kw=grid_import, grid_export_kw=grid_export)
    assert abs(dp_day(cb, fi, imp, exp, cap, p) - brute(cb, fi, imp, exp, cap, p)) < 1e-9
    # a limit never helps (AK-19)
    free = replace(p, grid_import_kw=0.0, grid_export_kw=0.0)
    assert dp_day(cb, fi, imp, exp, cap, p) >= dp_day(cb, fi, imp, exp, cap, free) - 1e-9
