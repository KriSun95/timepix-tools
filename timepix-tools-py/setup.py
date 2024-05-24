import setuptools

setuptools.setup(
    name="timepix_tools_py",
    version="0.0.1",
    description="Software used for the Timepix system.",
    url="https://github.com/foxsi/timepix-tools",
    install_requires=[
            "numpy", 
            "scipy",
            "matplotlib"
        ],
    packages=setuptools.find_packages(),
    zip_safe=False
)