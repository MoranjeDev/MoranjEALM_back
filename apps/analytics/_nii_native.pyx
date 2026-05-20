# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
"""
Hot path Cython — calcul NII Sensitivity vectorisé.

Compilé en .so natif au build production : non décompilable au niveau Python.
Le .py de fallback (nii.py) reste utilisable en développement.

Une fois la phase 5 industrialisée, importer ce module dans nii.py via :
    try:
        from apps.analytics._nii_native import compute_nii_native as compute_nii_sensitivity
    except ImportError:
        # fallback Python pour le dev
        ...
"""
import numpy as np
cimport numpy as np
from libc.math cimport fabs


def compute_nii_native(
    double[:] amounts,
    double[:] rates,
    int[:] horizon_class,   # 0=short, 1=medium, 2=long
    int[:] sides,            # 0=asset, 1=liability
    double parallel_bp,
    double short_bp,
    double long_bp,
    int horizon_days,
):
    """
    Calcule le NII pour un scénario donné.

    Tous les arguments sont des memoryviews NumPy : zéro copie.
    """
    cdef Py_ssize_t n = amounts.shape[0]
    cdef double revenue = 0.0
    cdef double cost = 0.0
    cdef double rate, shift, applied, amount, time_factor
    cdef int h_class, side
    cdef Py_ssize_t i

    time_factor = horizon_days / 365.0

    for i in range(n):
        amount = amounts[i]
        rate = rates[i]
        h_class = horizon_class[i]
        side = sides[i]

        if parallel_bp != 0.0:
            shift = parallel_bp / 10000.0
        elif h_class == 0:  # short
            shift = short_bp / 10000.0
        else:               # long ou medium (interpolé en amont)
            shift = long_bp / 10000.0

        applied = (rate / 100.0) + shift

        if side == 0:
            revenue += amount * applied * time_factor
        else:
            cost += amount * applied * time_factor

    return revenue, cost, revenue - cost
