"""
Pied Piper - O compressor de imagens mais eficiente da Internet.

Formato de arquivo .PP para compressao e descompressao de imagens
usando o algoritmo exclusivo Middle-Out Compression.

Uso rapido:
    from pied_piper import compress, decompress

    stats = compress("foto.png", "foto.PP")
    stats = decompress("foto.PP", "foto_restaurada.png")
"""

__version__ = "2.0.0"
__author__ = "Pied Piper"
__license__ = "Proprietary"

from pied_piper.codec import compress, decompress, info
