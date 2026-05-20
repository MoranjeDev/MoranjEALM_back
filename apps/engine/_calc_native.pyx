# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
"""
Hot path Cython — bucketization rapide des montants par maturité.

Utilisé par synthesis.py pour la production des outputs.
"""
import numpy as np
cimport numpy as np


def bucketize_native(
    double[:] amounts,
    long[:] dates_ns,         # timestamps en nanosecondes (numpy datetime64[ns])
    long[:] bucket_starts_ns,
    long[:] bucket_ends_ns,   # -1 pour le bucket ouvert
):
    """
    Pour chaque ligne (amounts[i], dates_ns[i]), trouve son bucket et
    accumule. Retourne un array float64 de longueur N_BUCKETS.
    """
    cdef Py_ssize_t n = amounts.shape[0]
    cdef Py_ssize_t nb = bucket_starts_ns.shape[0]
    cdef double[:] out = np.zeros(nb, dtype=np.float64)
    cdef Py_ssize_t i, j
    cdef long d
    cdef double a

    for i in range(n):
        d = dates_ns[i]
        a = amounts[i]
        for j in range(nb):
            if d >= bucket_starts_ns[j]:
                if bucket_ends_ns[j] == -1 or d < bucket_ends_ns[j]:
                    out[j] += a
                    break
    return np.asarray(out)
