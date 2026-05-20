"""
Compilation des modules Cython sensibles.

Lancé pendant le build production (Dockerfile.prod) :
    python setup_cython.py build_ext --inplace

Cela produit des fichiers .so / .pyd compilés C, beaucoup plus difficiles
à rétro-concevoir que du Python pur.
"""
from setuptools import setup
from Cython.Build import cythonize


CYTHON_MODULES = [
    "apps/engine/_calc_native.pyx",
    "apps/analytics/_nii_native.pyx",
    "apps/analytics/_eve_native.pyx",
]


setup(
    name="moranjealm-cython",
    ext_modules=cythonize(
        CYTHON_MODULES,
        compiler_directives={
            "language_level": "3",
            "boundscheck": False,
            "wraparound": False,
            "cdivision": True,
            "embedsignature": False,
        },
        annotate=False,
    ),
    zip_safe=False,
)
