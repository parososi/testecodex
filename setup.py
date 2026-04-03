from setuptools import setup, find_packages

setup(
    name='pied-piper',
    version='1.0.0',
    description='Pied Piper - O compressor de imagens mais eficiente da Internet',
    packages=find_packages(),
    python_requires='>=3.8',
    install_requires=[
        'Pillow>=10.0.0',
        'numpy>=1.24.0',
    ],
    entry_points={
        'console_scripts': [
            'pied-piper=pied_piper.cli:main',
        ],
    },
)
