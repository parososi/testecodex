"""
Pied Piper - Compressor universal de arquivos com algoritmo Middle-Out.

Formato .PP para compressao e descompressao de QUALQUER tipo de arquivo:
imagens (lossy/lossless), texto, binarios, audio, video, documentos, etc.

Uso rapido:
    from pied_piper import compress, decompress, compress_file, decompress_file

    stats = compress("foto.png", "foto.PP")         # imagem
    stats = compress_file("dados.csv", "dados.PP")   # qualquer arquivo
    stats = decompress("foto.PP", "foto_out.png")
    stats = decompress_file("dados.PP")
"""

__version__ = "4.0.0"
__author__ = "Pied Piper"
__license__ = "Proprietary"

from pied_piper.codec import (
    compress, decompress, info, compress_folder, decompress_bundle, is_bundle,
    compress_file, decompress_file, is_universal, smart_compress, smart_decompress,
)
