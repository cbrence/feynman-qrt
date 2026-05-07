from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="quant-research-toolkit",
    version="1.0.0",
    author="Colin Brence",
    description="Multi-source academic search and gap analysis for quantitative finance",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "qrt-search=qrt.cli:search_main",
            "qrt-kg=qrt.cli:kg_main",
            "qrt-gaps=qrt.cli:gaps_main",
        ],
    },
)
