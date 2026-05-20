# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
"""
Hot path Cython — calcul EVE Sensitivity vectorisé.

Implémente la formule :
    EVE = Σ amount_i * exp(-(rate_i + shock(t_i)) * t_i)
"""
import numpy as np
cimport numpy as np
from libc.math cimport exp


def compute_eve_native(
    double[:] amounts,
    double[:] rates,
    double[:] times_years,
    int[:] sides,            # 0=asset, 1=liability
    double parallel_bp,
    double short_bp,
    double long_bp,
):
    """Retourne (pv_assets, pv_liabilities, eve)."""
    cdef Py_ssize_t n = amounts.shape[0]
    cdef double pv_a = 0.0
    cdef double pv_l = 0.0
    cdef double rate, shift, t, df, pv, weight
    cdef Py_ssize_t i

    for i in range(n):
        t = times_years[i]
        rate = rates[i] / 100.0

        if parallel_bp != 0.0:
            shift = parallel_bp / 10000.0
        elif t <= 1.0:
            shift = short_bp / 10000.0
        elif t > 5.0:
            shift = long_bp / 10000.0
        else:
            weight = (t - 1.0) / 4.0
            shift = ((1.0 - weight) * short_bp + weight * long_bp) / 10000.0

        # Floor à -1 %
        if (rate + shift) < -0.01:
            rate = -0.01 - shift

        df = exp(-(rate + shift) * t)
        pv = amounts[i] * df

        if sides[i] == 0:
            pv_a += pv
        else:
            pv_l += pv

    return pv_a, pv_l, pv_a - pv_l
