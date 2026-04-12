"""
Delta Encoding para dados com padroes sequenciais

Codifica diferencas entre bytes consecutivos. Muito eficaz para:
  - Dados de sensores com mudancas incrementais
  - Audio PCM nao comprimido (WAV)
  - Tabelas numericas
  - Binarios com padroes regulares

Inspirado no filtro Delta do 7-Zip e no pre-processamento
do WinRAR para dados de audio.

O delta encoding reduz a entropia dos dados quando ha
correlacao entre bytes adjacentes, permitindo que compressores
subsequentes (LZMA, zlib) obtenham melhores taxas.
"""

import struct


def delta_compress(data: bytes) -> bytes:
    """
    Aplica delta encoding: cada byte armazena a diferenca para o anterior.

    Formato:
      [4 bytes: tamanho original LE]
      [1 byte: primeiro byte (referencia)]
      [N-1 bytes: deltas (byte[i] - byte[i-1]) mod 256]
    """
    if not data:
        return struct.pack('<I', 0)

    n = len(data)
    out = bytearray()
    out += struct.pack('<I', n)
    out.append(data[0])

    for i in range(1, n):
        delta = (data[i] - data[i - 1]) & 0xFF
        out.append(delta)

    return bytes(out)


def delta_decompress(data: bytes) -> bytes:
    """Reverte delta encoding."""
    if len(data) < 4:
        return b''

    original_size = struct.unpack('<I', data[:4])[0]
    if original_size == 0:
        return b''

    result = bytearray(original_size)
    result[0] = data[4]

    for i in range(1, min(original_size, len(data) - 4)):
        result[i] = (result[i - 1] + data[4 + i]) & 0xFF

    return bytes(result)
