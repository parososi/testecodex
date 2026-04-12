"""
Run-Length Encoding (RLE) para dados com muitas repeticoes

Codifica sequencias de bytes identicos como (contagem, byte).
Eficaz para:
  - Imagens com areas de cor solida
  - Dados com muitos zeros
  - Arquivos esparsos

Inspirado no RLE do formato BMP e do PackBits do TIFF.
"""

import struct


def rle_compress(data: bytes) -> bytes:
    """
    Comprime dados usando RLE.

    Formato:
      [4 bytes: tamanho original LE]
      Sequencia de pares:
        [1 byte: contagem (1-255)]
        [1 byte: valor]
      Contagem 0 = fim dos dados
    """
    if not data:
        return struct.pack('<I', 0)

    n = len(data)
    out = bytearray()
    out += struct.pack('<I', n)

    i = 0
    while i < n:
        current = data[i]
        count = 1
        while i + count < n and data[i + count] == current and count < 255:
            count += 1
        out.append(count)
        out.append(current)
        i += count

    return bytes(out)


def rle_decompress(data: bytes) -> bytes:
    """Descomprime dados produzidos por rle_compress."""
    if len(data) < 4:
        return b''

    original_size = struct.unpack('<I', data[:4])[0]
    if original_size == 0:
        return b''

    result = bytearray()
    pos = 4

    while pos + 1 < len(data) and len(result) < original_size:
        count = data[pos]
        value = data[pos + 1]
        pos += 2
        if count == 0:
            break
        result.extend(bytes([value]) * count)

    return bytes(result[:original_size])
