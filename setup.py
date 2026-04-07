from setuptools import setup, find_packages

setup(
    name='pied-piper',
    version='2.0.0',
    description='Pied Piper - Middle-Out Image Compression (.PP format)',
    long_description='High-performance image compressor using the exclusive '
                     'Middle-Out Compression algorithm with a C engine.',
    packages=find_packages(),
    python_requires='>=3.8',
    install_requires=[
        'Pillow>=10.0.0',
        'numpy>=1.24.0',
    ],
    entry_points={
        'console_scripts': [
            'pp=pied_piper.cli:main',
            'pied-piper=pied_piper.cli:main',
        ],
    },
)
