from setuptools import setup
from Cython.Build import cythonize

setup(
    ext_modules=cythonize(
        "matching_engine_core/order_book.pyx",
        compiler_directives={"language_level": "3"},
    )
)