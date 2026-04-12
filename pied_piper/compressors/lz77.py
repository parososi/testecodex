"""
LZ77 Sliding Window Compression

Algoritmo de compressao baseado em dicionario com janela deslizante.
Inspirado no LZ77 (Lempel-Ziv, 1977) usado como base pelo DEFLATE (gzip/ZIP)
e pelo LZSS usado no 7-Zip e WinRAR.

O algoritmo procura repeticoes em uma janela de dados ja processados
e codifica matches como (distancia, comprimento) ao inves de repetir bytes.

Referencia: Ziv & Lempel, "A Universal Algorithm for Sequential Data Compression", 1977
"""

import struct

# Parametros da janela (inspirados no DEFLATE)
WINDOW_SIZE = 32768      # 32 KB janela de busca
MIN_MATCH = 3            # Match minimo (como DEFLATE)
MAX_MATCH = 258          # Match maximo (como DEFLATE)


def lz77_compress(data: bytes) -> bytes:
    """
    Comprime dados usando LZ77 com janela deslizante.

    Formato:
      [4 bytes: tamanho original LE]
      Sequencia de tokens:
        Literal:  [0x00] [1 byte: valor]
        Match:    [0x01] [2 bytes: distancia LE] [2 bytes: comprimento LE]
    """
    if not data:
        return struct.pack('<I', 0)

    n = len(data)
    out = bytearray()
    out += struct.pack('<I', n)

    pos = 0

    while pos < n:
        best_dist = 0
        best_len = 0

        # Busca na janela
        search_start = max(0, pos - WINDOW_SIZE)

        if pos + MIN_MATCH <= n:
            # Hash rapido para encontrar candidatos
            target = data[pos:pos + MIN_MATCH]

            scan = search_start
            while scan < pos:
                # Encontra a proxima ocorrencia do prefixo
                idx = data.find(target, scan, pos)
                if idx == -1:
                    break

                # Extende o match
                match_len = MIN_MATCH
                while (match_len < MAX_MATCH and
                       pos + match_len < n and
                       data[idx + match_len] == data[pos + match_len]):
                    match_len += 1

                dist = pos - idx
                if match_len > best_len:
                    best_len = match_len
                    best_dist = dist

                scan = idx + 1

        if best_len >= MIN_MATCH:
            out.append(0x01)
            out += struct.pack('<HH', best_dist, best_len)
            pos += best_len
        else:
            out.append(0x00)
            out.append(data[pos])
            pos += 1

    return bytes(out)


def lz77_decompress(data: bytes) -> bytes:
    """Descomprime dados produzidos por lz77_compress."""
    if len(data) < 4:
        return b''

    original_size = struct.unpack('<I', data[:4])[0]
    if original_size == 0:
        return b''

    result = bytearray()
    pos = 4

    while pos < len(data) and len(result) < original_size:
        token_type = data[pos]
        pos += 1

        if token_type == 0x00:
            # Literal
            if pos < len(data):
                result.append(data[pos])
                pos += 1
        elif token_type == 0x01:
            # Match
            if pos + 4 <= len(data):
                dist, length = struct.unpack('<HH', data[pos:pos + 4])
                pos += 4
                start = len(result) - dist
                for i in range(length):
                    result.append(result[start + i])

    return bytes(result[:original_size])
