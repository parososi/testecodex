"""
Pied Piper - Modulos de Compressao Lossless

Algoritmos disponiveis:
  - BWT:     Burrows-Wheeler Transform + Move-to-Front (inspirado bzip2)
  - Huffman: Codificacao Huffman canonica
  - LZ77:    Sliding window compression (inspirado DEFLATE/7-Zip)
  - Delta:   Delta encoding para dados com padroes sequenciais
  - RLE:     Run-Length Encoding para dados com repeticoes

Pipeline:
  - pipeline.py: Seleciona automaticamente o melhor algoritmo
                 entre LZMA, BZ2, DEFLATE, e BWT+MTF+Huffman
"""

from pied_piper.compressors.bwt import bwt_compress, bwt_decompress
from pied_piper.compressors.huffman import huffman_compress, huffman_decompress
from pied_piper.compressors.lz77 import lz77_compress, lz77_decompress
from pied_piper.compressors.delta import delta_compress, delta_decompress
from pied_piper.compressors.rle import rle_compress, rle_decompress
from pied_piper.compressors.pipeline import (
    compress_universal, decompress_universal,
    STRATEGY_LZMA, STRATEGY_BZ2, STRATEGY_DEFLATE, STRATEGY_BWT,
    STRATEGY_DELTA_LZMA, STRATEGY_STORED,
)
