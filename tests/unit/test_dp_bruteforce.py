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
                c += (bus - ab) * cb[h] + ab * fi[h] + p.wear * k * q
            elif k < 0:
                d = -k * q * eta
                use = min(d, imp[h])
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
