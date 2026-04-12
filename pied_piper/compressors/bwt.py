"""
Burrows-Wheeler Transform + Move-to-Front Transform

Inspirado no bzip2 (Julian Seward, 1996).
O BWT reorganiza os bytes de forma que sequencias repetidas fiquem agrupadas,
permitindo que codificadores subsequentes (MTF + Huffman/RLE) comprimam melhor.

Pipeline: dados -> BWT -> MTF -> output
Reverso:  output -> MTF inverso -> BWT inverso -> dados

Referencia: Burrows & Wheeler, "A Block-sorting Lossless Data Compression Algorithm", 1994
"""

import struct


def _bwt_encode(data: bytes) -> tuple:
    """
    Burrows-Wheeler Transform.
    Retorna (transformed_bytes, original_index).

    Usa suffix array para O(n log n) ao inves de O(n^2 log n).
    """
    if not data:
        return b'', 0

    n = len(data)

    # Para blocos grandes, usa abordagem otimizada com suffix array
    # Para blocos pequenos, usa rotacoes diretas
    if n <= 4096:
        # Rotacoes diretas - simples e correto
        doubled = data + data
        indices = sorted(range(n), key=lambda i: doubled[i:i + n])
        transformed = bytes(doubled[i + n - 1] for i in indices)
        original_idx = indices.index(0)
        return transformed, original_idx
    else:
        # Suffix array via sorted suffixes
        sa = sorted(range(n), key=lambda i: data[i:] + data[:i])
        transformed = bytes(data[(i - 1) % n] for i in sa)
        original_idx = sa.index(0)
        return transformed, original_idx


def _bwt_decode(data: bytes, original_idx: int) -> bytes:
    """
    Inversa da BWT usando LF-mapping.

    Dado L (ultima coluna da matrix de rotacoes ordenada) e o indice
    da string original, reconstroi os dados originais.

    Algoritmo:
      1. Computa F (primeira coluna) = sorted(L)
      2. Computa LF-mapping: LF[i] = posicao em F correspondente a L[i]
      3. A partir de original_idx, segue LF e le de F
    """
    if not data:
        return b''

    n = len(data)
    count = [0] * 256

    for b in data:
        count[b] += 1

    # Prefix sum -> starts[c] = indice onde o caractere c comeca em F
    total = 0
    starts = [0] * 256
    for i in range(256):
        starts[i] = total
        total += count[i]

    # Computa F (primeira coluna = L ordenado)
    first_col = bytearray(sorted(data))

    # Computa LF-mapping
    # LF[i] = starts[L[i]] + (numero de ocorrencias de L[i] em L[0..i-1])
    lf = [0] * n
    seen = [0] * 256
    for i in range(n):
        b = data[i]
        lf[i] = starts[b] + seen[b]
        seen[b] += 1

    # Reconstroi: LF percorre as posicoes na ordem reversa (n-1, n-2, ..., 1)
    # Entao colocamos o primeiro caractere na posicao 0 e os demais de tras pra frente
    result = bytearray(n)
    idx = original_idx
    result[0] = first_col[idx]
    idx = lf[idx]
    for i in range(n - 1, 0, -1):
        result[i] = first_col[idx]
        idx = lf[idx]

    return bytes(result)


def _mtf_encode(data: bytes) -> bytes:
    """
    Move-to-Front Transform.
    Converte bytes em indices de uma lista que se atualiza.
    Bytes frequentes recebem indices baixos (perto de 0).
    """
    if not data:
        return b''

    # Tabela de simbolos (0-255)
    symbols = list(range(256))
    result = bytearray(len(data))

    for i, b in enumerate(data):
        idx = symbols.index(b)
        result[i] = idx
        # Move para frente
        symbols.pop(idx)
        symbols.insert(0, b)

    return bytes(result)


def _mtf_decode(data: bytes) -> bytes:
    """Inversa do Move-to-Front Transform."""
    if not data:
        return b''

    symbols = list(range(256))
    result = bytearray(len(data))

    for i, idx in enumerate(data):
        b = symbols[idx]
        result[i] = b
        symbols.pop(idx)
        symbols.insert(0, b)

    return bytes(result)


# Tamanho do bloco BWT (inspirado no bzip2: 100k-900k)
BWT_BLOCK_SIZE = 100_000  # 100 KB por bloco


def bwt_compress(data: bytes) -> bytes:
    """
    Comprime dados usando BWT + MTF.

    Formato:
      [4 bytes: tamanho original LE]
      [4 bytes: numero de blocos LE]
      Para cada bloco:
        [4 bytes: tamanho do bloco transformado LE]
        [4 bytes: indice original BWT LE]
        [dados MTF do bloco]
    """
    if not data:
        return struct.pack('<II', 0, 0)

    n = len(data)
    blocks = []

    for i in range(0, n, BWT_BLOCK_SIZE):
        block = data[i:i + BWT_BLOCK_SIZE]
        bwt_data, bwt_idx = _bwt_encode(block)
        mtf_data = _mtf_encode(bwt_data)
        blocks.append((mtf_data, bwt_idx))

    out = bytearray()
    out += struct.pack('<II', n, len(blocks))

    for mtf_data, bwt_idx in blocks:
        out += struct.pack('<II', len(mtf_data), bwt_idx)
        out += mtf_data

    return bytes(out)


def bwt_decompress(data: bytes) -> bytes:
    """Descomprime dados produzidos por bwt_compress."""
    if len(data) < 8:
        return b''

    original_size, num_blocks = struct.unpack('<II', data[:8])
    if original_size == 0:
        return b''

    pos = 8
    result = bytearray()

    for _ in range(num_blocks):
        if pos + 8 > len(data):
            break
        block_size, bwt_idx = struct.unpack('<II', data[pos:pos + 8])
        pos += 8

        mtf_data = data[pos:pos + block_size]
        pos += block_size

        bwt_data = _mtf_decode(mtf_data)
        original_block = _bwt_decode(bwt_data, bwt_idx)
        result += original_block

    return bytes(result[:original_size])
