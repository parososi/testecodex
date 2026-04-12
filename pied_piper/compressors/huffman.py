"""
Codificacao Huffman Canonica

Implementacao de Huffman coding para compressao lossless de dados.
Inspirado na codificacao usada internamente pelo DEFLATE (RFC 1951)
e pelo codec de entropia do 7-Zip.

Referencia: David A. Huffman, "A Method for the Construction of
           Minimum-Redundancy Codes", 1952
"""

import heapq
import struct


class _HuffNode:
    __slots__ = ('freq', 'byte', 'left', 'right')

    def __init__(self, freq, byte=None, left=None, right=None):
        self.freq = freq
        self.byte = byte
        self.left = left
        self.right = right

    def __lt__(self, other):
        return self.freq < other.freq


def _build_tree(freq_table: list) -> _HuffNode:
    """Constroi arvore de Huffman a partir de tabela de frequencias."""
    heap = []
    for byte_val, freq in enumerate(freq_table):
        if freq > 0:
            heapq.heappush(heap, _HuffNode(freq, byte=byte_val))

    if not heap:
        return None
    if len(heap) == 1:
        node = heapq.heappop(heap)
        return _HuffNode(node.freq, left=node)

    while len(heap) > 1:
        left = heapq.heappop(heap)
        right = heapq.heappop(heap)
        parent = _HuffNode(left.freq + right.freq, left=left, right=right)
        heapq.heappush(heap, parent)

    return heap[0]


def _build_codes(root: _HuffNode) -> dict:
    """Gera tabela de codigos a partir da arvore."""
    if root is None:
        return {}

    codes = {}

    def _walk(node, code):
        if node is None:
            return
        if node.byte is not None:
            codes[node.byte] = code if code else '0'
            return
        _walk(node.left, code + '0')
        _walk(node.right, code + '1')

    _walk(root, '')
    return codes


def huffman_compress(data: bytes) -> bytes:
    """
    Comprime dados usando Huffman coding.

    Formato:
      [4 bytes: tamanho original LE]
      [2 bytes: numero de simbolos na tabela LE]
      Para cada simbolo:
        [1 byte: valor do byte]
        [1 byte: comprimento do codigo]
      [4 bytes: total de bits nos dados LE]
      [dados codificados em Huffman, empacotados em bytes]
    """
    if not data:
        return struct.pack('<I', 0)

    # Frequencias
    freq = [0] * 256
    for b in data:
        freq[b] += 1

    # Arvore e codigos
    tree = _build_tree(freq)
    codes = _build_codes(tree)

    if not codes:
        return struct.pack('<I', 0)

    # Codifica dados em bitstream
    bits = []
    for b in data:
        bits.append(codes[b])
    bitstring = ''.join(bits)
    total_bits = len(bitstring)

    # Empacota bits em bytes
    pad = (8 - total_bits % 8) % 8
    bitstring += '0' * pad
    encoded = bytearray()
    for i in range(0, len(bitstring), 8):
        encoded.append(int(bitstring[i:i + 8], 2))

    # Serializa tabela de codigos (formato canonico)
    # Ordena por comprimento de codigo, depois por valor
    sorted_codes = sorted(codes.items(), key=lambda x: (len(x[1]), x[0]))

    out = bytearray()
    out += struct.pack('<I', len(data))
    out += struct.pack('<H', len(sorted_codes))

    for byte_val, code in sorted_codes:
        out.append(byte_val)
        out.append(len(code))

    out += struct.pack('<I', total_bits)
    out += encoded

    return bytes(out)


def huffman_decompress(data: bytes) -> bytes:
    """Descomprime dados produzidos por huffman_compress."""
    if len(data) < 4:
        return b''

    original_size = struct.unpack('<I', data[:4])[0]
    if original_size == 0:
        return b''

    pos = 4
    num_symbols = struct.unpack('<H', data[pos:pos + 2])[0]
    pos += 2

    # Reconstroi tabela de codigos
    code_lengths = []
    for _ in range(num_symbols):
        byte_val = data[pos]
        code_len = data[pos + 1]
        code_lengths.append((byte_val, code_len))
        pos += 2

    # Reconstroi codigos canonicos
    # Agrupa por comprimento
    code_lengths.sort(key=lambda x: (x[1], x[0]))

    codes_map = {}
    code_val = 0
    prev_len = 0

    for byte_val, clen in code_lengths:
        if prev_len > 0:
            code_val = (code_val + 1) << (clen - prev_len)
        code_str = bin(code_val)[2:].zfill(clen)
        codes_map[code_str] = byte_val
        prev_len = clen

    total_bits = struct.unpack('<I', data[pos:pos + 4])[0]
    pos += 4

    # Decodifica bitstream
    encoded_bytes = data[pos:]
    bitstring = ''.join(bin(b)[2:].zfill(8) for b in encoded_bytes)
    bitstring = bitstring[:total_bits]

    result = bytearray()
    current = ''
    for bit in bitstring:
        current += bit
        if current in codes_map:
            result.append(codes_map[current])
            current = ''
            if len(result) >= original_size:
                break

    return bytes(result[:original_size])
