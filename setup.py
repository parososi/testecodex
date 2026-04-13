from setuptools import setup, find_packages

setup(
    name='pied-piper',
    version='4.0.0',
    description='Pied Piper - Universal File Compression with Middle-Out Algorithm (.PP format)',
    long_description='Universal file compressor supporting any file type: images (lossy/lossless), '
                     'text, binary, audio, video, documents. Uses multi-algorithm pipeline '
                     '(LZMA, BZ2, DEFLATE, BWT+MTF, Delta+LZMA) with automatic strategy selection.',
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
