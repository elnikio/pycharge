import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="pycharge",
    version="1.0a3",
    author="Matthew Filipovich",
    author_email="matthew.filipovich@queensu.ca",
    description="Electrodynamics simulator for calculating the fields and potentials generated by moving point charges and simulating oscillating dipoles.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/MatthewFilipovich/pycharge",
    project_urls={
        "Documentation" : "https://pycharge.readthedocs.io/",
        "Bug Tracker": "https://github.com/MatthewFilipovich/pycharge/issues",
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
        "Intended Audience :: Science/Research",
        "Intended Audience :: Education",
        "Topic :: Scientific/Engineering :: Physics",
        "Topic :: Scientific/Engineering :: Visualization"
    ],
    license="GNU General Public License v3 (GPLv3)",
    packages=setuptools.find_packages(where="."),
    python_requires=">=3.7",
    install_requires=[
        'numpy',
        'dill',
        'scipy',
        'matplotlib',
        'tqdm'
    ],
    extras_require={"MPI":  ['mpi4py']}
)
