"""
Pied Piper Codec - Motor de compressao universal.

Este modulo gerencia todo o pipeline de compressao/descompressao .PP
para QUALQUER tipo de arquivo, nao apenas imagens.

Modos suportados:
  - Imagens Lossy  (padrao): DCT + quantizacao adaptativa + espiral Middle-Out
  - Imagens Lossless (-l):   DPCM entre blocos na espiral Middle-Out, sem perdas
  - Arquivos universais:     Multi-algoritmo (LZMA/BZ2/DEFLATE/BWT+MTF)
                             Sempre lossless, inspirado no 7-Zip e WinRAR

Tipos de arquivo suportados:
  - Imagens: PNG, JPEG, BMP, TIFF, GIF, WEBP, etc. (via Pillow)
  - Texto: TXT, CSV, JSON, XML, HTML, MD, LOG, etc.
  - Codigo: PY, JS, TS, C, CPP, H, JAVA, RS, GO, etc.
  - Documentos: PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX, ODT, etc.
  - Audio: WAV, FLAC, MP3, OGG, AAC, etc.
  - Video: MP4, AVI, MKV, MOV, WEBM, etc.
  - Executaveis: EXE, DLL, SO, BIN, etc.
  - Arquivos: ZIP, TAR, GZ, 7Z, RAR (armazenados sem recompressao)
  - Qualquer outro formato binario ou texto
"""

import ctypes
import hashlib
import json
import os
import struct
import sys
import time
import zlib
from ctypes import c_double, c_int, c_int16, c_uint8, c_uint32, POINTER, Structure

import numpy as np
from PIL import Image, ImageFile

# Permite carregar imagens truncadas sem erro fatal
ImageFile.LOAD_TRUNCATED_IMAGES = True

# ==============================================================
# Constantes do formato .PP
# ==============================================================

PP_MAGIC = b'PPMO'          # Pied Piper Middle-Out
PP_VERSION = 4              # v4: planos de frequencia + DPCM horizontal (numpy puro)
PP_EXTENSION = '.PP'

# ==============================================================
# Tabelas de quantizacao
# ==============================================================

QUANT_LUMINANCE = np.array([
    [16, 11, 10, 16,  24,  40,  51,  61],
    [12, 12, 14, 19,  26,  58,  60,  55],
    [14, 13, 16, 24,  40,  57,  69,  56],
    [14, 17, 22, 29,  51,  87,  80,  62],
    [18, 22, 37, 56,  68, 109, 103,  77],
    [24, 35, 55, 64,  81, 104, 113,  92],
    [49, 64, 78, 87, 103, 121, 120, 101],
    [72, 92, 95, 98, 112, 100, 103,  99],
], dtype=np.float64)

QUANT_CHROMINANCE = np.array([
    [17, 18, 24, 47, 99, 99, 99, 99],
    [18, 21, 26, 66, 99, 99, 99, 99],
    [24, 26, 56, 99, 99, 99, 99, 99],
    [47, 66, 99, 99, 99, 99, 99, 99],
    [99, 99, 99, 99, 99, 99, 99, 99],
    [99, 99, 99, 99, 99, 99, 99, 99],
    [99, 99, 99, 99, 99, 99, 99, 99],
    [99, 99, 99, 99, 99, 99, 99, 99],
], dtype=np.float64)

# Mapeamento zigzag: posicao i no zigzag → indice row-major no bloco 8x8
# Concentra coeficientes de alta energia no inicio, trailing zeros sao implicitos
ZIGZAG_IDX = np.array([
     0,  1,  8, 16,  9,  2,  3, 10,
    17, 24, 32, 25, 18, 11,  4,  5,
    12, 19, 26, 33, 40, 48, 41, 34,
    27, 20, 13,  6,  7, 14, 21, 28,
    35, 42, 49, 56, 57, 50, 43, 36,
    29, 22, 15, 23, 30, 37, 44, 51,
    58, 59, 52, 45, 38, 31, 39, 46,
    53, 60, 61, 54, 47, 55, 62, 63,
], dtype=np.int32)


# ==============================================================
# Carregamento do motor C
# ==============================================================

class MOStats(Structure):
    _fields_ = [
        ('total_blocks', c_uint32),
        ('zero_blocks', c_uint32),
        ('predicted_blocks', c_uint32),
        ('avg_energy', c_double),
        ('sparsity', c_double),
    ]


# Tipo int16 pointer para funcoes lossless
c_int16_p = POINTER(c_int16)


def _find_engine_library():
    """Localiza a biblioteca libmiddleout compilada."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, '..', 'engine', 'libmiddleout.so'),
        os.path.join(here, '..', 'engine', 'libmiddleout.dylib'),
        os.path.join(here, '..', 'engine', 'libmiddleout.dll'),
        os.path.join(here, 'libmiddleout.so'),
        os.path.join(here, 'libmiddleout.dylib'),
        os.path.join(here, 'libmiddleout.dll'),
        '/usr/local/lib/libmiddleout.so',
    ]
    for path in candidates:
        if os.path.exists(path):
            return os.path.abspath(path)
    return None


_LIB = None
_LIBC = None
_USE_C_ENGINE = False


def _load_engine():
    """Carrega o motor C via ctypes, se disponivel."""
    global _LIB, _LIBC, _USE_C_ENGINE
    if _LIB is not None:
        return _LIB

    lib_path = _find_engine_library()
    if not lib_path:
        return None

    try:
        lib = ctypes.CDLL(lib_path)

        # mo_compress_channel(channel, width, height, quant_table, quality, &compressed_size, &stats)
        lib.mo_compress_channel.restype = ctypes.c_void_p
        lib.mo_compress_channel.argtypes = [
            POINTER(c_double), c_int, c_int,
            POINTER(c_double), c_int,
            POINTER(c_int), POINTER(MOStats),
        ]

        # mo_decompress_channel(compressed, compressed_size, width, height, quant_table, quality)
        lib.mo_decompress_channel.restype = ctypes.c_void_p
        lib.mo_decompress_channel.argtypes = [
            POINTER(c_uint8), c_int, c_int, c_int,
            POINTER(c_double), c_int,
        ]

        # libc para free() — cross-platform (Unix usa None, Windows usa msvcrt)
        try:
            libc = ctypes.CDLL(None)
        except OSError:
            try:
                libc = ctypes.CDLL("msvcrt")  # Windows
            except OSError:
                libc = ctypes.CDLL("libc.so.6")  # Linux fallback
        libc.free.argtypes = [ctypes.c_void_p]
        libc.free.restype = None

        # mo_compress_lossless_ch(channel, width, height, &out_size, &stats)
        lib.mo_compress_lossless_ch.restype = ctypes.c_void_p
        lib.mo_compress_lossless_ch.argtypes = [
            c_int16_p, c_int, c_int,
            POINTER(c_int), POINTER(MOStats),
        ]

        # mo_decompress_lossless_ch(data, data_size, width, height)
        lib.mo_decompress_lossless_ch.restype = ctypes.c_void_p
        lib.mo_decompress_lossless_ch.argtypes = [
            POINTER(c_uint8), c_int, c_int, c_int,
        ]

        # mo_psnr(original, restored, size, max_val)
        lib.mo_psnr.restype = c_double
        lib.mo_psnr.argtypes = [
            POINTER(c_double), POINTER(c_double), c_int, c_double,
        ]

        _LIB = lib
        _LIBC = libc
        _USE_C_ENGINE = True
        return lib
    except OSError:
        return None


# ==============================================================
# Conversoes de espaco de cor
# ==============================================================

def _rgb_to_ycbcr(rgb: np.ndarray) -> np.ndarray:
    """Converte RGB [H,W,3] para YCbCr [H,W,3]."""
    rgb = rgb.astype(np.float64)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    y  =  0.299 * r + 0.587 * g + 0.114 * b
    cb = -0.168736 * r - 0.331264 * g + 0.5 * b + 128
    cr =  0.5 * r - 0.418688 * g - 0.081312 * b + 128
    return np.stack([y, cb, cr], axis=-1)


def _ycbcr_to_rgb(ycbcr: np.ndarray) -> np.ndarray:
    """Converte YCbCr [H,W,3] para RGB uint8 [H,W,3]."""
    y  = ycbcr[..., 0]
    cb = ycbcr[..., 1] - 128
    cr = ycbcr[..., 2] - 128
    r = y + 1.402 * cr
    g = y - 0.344136 * cb - 0.714136 * cr
    b = y + 1.772 * cb
    rgb = np.stack([r, g, b], axis=-1)
    return np.clip(rgb, 0, 255).astype(np.uint8)


def _subsample_420(channel: np.ndarray) -> np.ndarray:
    """Subamostragem 4:2:0 (reduz pela metade em cada eixo). Garante tamanho minimo 1x1."""
    h, w = channel.shape
    # Dimensoes minimas: 2x2 para permitir subamostragem
    if h < 2 or w < 2:
        # Retorna a media do canal inteiro como bloco 1x1
        return np.full((max(1, h // 2 or 1), max(1, w // 2 or 1)),
                       channel.mean(), dtype=np.float64)
    h2 = h - (h % 2)
    w2 = w - (w % 2)
    crop = channel[:h2, :w2]
    return crop.reshape(h2 // 2, 2, w2 // 2, 2).mean(axis=(1, 3))


def _upsample_420(channel: np.ndarray, target_h: int, target_w: int) -> np.ndarray:
    """Reconstroi crominancia para dimensoes originais."""
    if channel.size == 0 or channel.shape[0] == 0 or channel.shape[1] == 0:
        return np.full((target_h, target_w), 128.0, dtype=np.float64)

    up = np.repeat(np.repeat(channel, 2, axis=0), 2, axis=1)

    # Se upsampled for menor que o alvo, faz padding replicando a ultima linha/coluna
    if up.shape[0] < target_h or up.shape[1] < target_w:
        uh, uw = up.shape
        padded = np.zeros((max(target_h, uh), max(target_w, uw)), dtype=up.dtype)
        padded[:uh, :uw] = up
        # Replica ultima linha, se preciso
        if uh < target_h and uh > 0:
            padded[uh:target_h, :uw] = up[uh - 1:uh, :]
        # Replica ultima coluna, se preciso
        if uw < target_w and uw > 0:
            padded[:target_h, uw:target_w] = padded[:target_h, uw - 1:uw]
        up = padded

    return up[:target_h, :target_w]


def _rct_forward(rgb: np.ndarray) -> tuple:
    """
    Transformada de Cor Reversivel (RCT - padrao JPEG 2000, ISO 15444-1).
    Converte RGB uint8 -> (Y, Cb, Cr) int16 SEM PERDAS.

    Y  = floor((R + 2*G + B) / 4)   faixa 0..255
    Cb = B - G                       faixa -255..255
    Cr = R - G                       faixa -255..255

    Inversamente: G = Y - floor((Cb+Cr)/4), R = Cr+G, B = Cb+G
    Garantia: reconstrucao exata para todo R,G,B em [0,255].
    """
    r = rgb[..., 0].astype(np.int32)
    g = rgb[..., 1].astype(np.int32)
    b = rgb[..., 2].astype(np.int32)
    y  = ((r + 2 * g + b) >> 2).astype(np.int16)
    cb = (b - g).astype(np.int16)
    cr = (r - g).astype(np.int16)
    return y, cb, cr


def _rct_inverse(y: np.ndarray, cb: np.ndarray, cr: np.ndarray) -> np.ndarray:
    """
    Inversa exata da RCT (JPEG 2000). Reconstroi RGB uint8 pixel-perfeito.
    """
    y32  = y.astype(np.int32)
    cb32 = cb.astype(np.int32)
    cr32 = cr.astype(np.int32)
    g = (y32 - ((cb32 + cr32) >> 2)).astype(np.uint8)
    r = (cr32 + g.astype(np.int32)).astype(np.uint8)
    b = (cb32 + g.astype(np.int32)).astype(np.uint8)
    return np.stack([r, g, b], axis=-1)


def _get_quant_table(base: np.ndarray, quality: int) -> np.ndarray:
    """Gera tabela de quantizacao escalada pela qualidade (1-100)."""
    quality = max(1, min(100, quality))
    if quality < 50:
        scale = 5000 / quality
    else:
        scale = 200 - 2 * quality
    table = np.floor((base * scale + 50) / 100)
    table = np.clip(table, 1, 255)
    return table


# ==============================================================
# Codec v4 — Numpy vetorizado (planos de frequencia + DPCM horizontal)
# Substitui o motor C para novos arquivos. Muito mais eficiente para zlib.
# ==============================================================

def _compress_channel_v4(channel: np.ndarray, quant_table: np.ndarray) -> tuple:
    """
    Comprime canal lossy v4: DCT vetorizado + zigzag + planos de frequencia.

    Formato de saida:
      [4 bytes: n_blocks LE]
      [64 * n_blocks * 2 bytes: planos de frequencia int16]
        Plano 0 (DC): DPCM entre blocos consecutivos (varredura raster)
        Planos 1-63 (AC): coeficientes zigzag brutos

    Retorna (bytes, stats_dict).
    """
    h, w = channel.shape
    bh = (h + 7) // 8
    bw = (w + 7) // 8
    ph, pw = bh * 8, bw * 8
    n_blocks = bh * bw

    # Padding com borda replicada
    padded = np.zeros((ph, pw), dtype=np.float64)
    padded[:h, :w] = channel
    if w < pw:
        padded[:h, w:] = channel[:, -1:]
    if h < ph:
        padded[h:, :] = padded[h - 1:h, :]

    # Reshape em blocos (n_blocks, 8, 8) e centraliza em 0
    blocks = (padded.reshape(bh, 8, bw, 8)
                    .transpose(0, 2, 1, 3)
                    .reshape(n_blocks, 8, 8) - 128.0)

    # DCT 2D vetorizado: D @ block @ D^T para todos os blocos de uma vez
    dct = (_DCT_M @ blocks) @ _DCT_MT      # (n_blocks, 8, 8)

    # Quantizacao com tabela fixa escalada pela qualidade
    qflat = quant_table.flatten()          # (64,)
    quant = np.round(dct.reshape(n_blocks, 64) / qflat).astype(np.int16)  # (n_blocks, 64)

    # Reordenacao zigzag: agrupa zeros no final de cada bloco
    zz = quant[:, ZIGZAG_IDX]             # (n_blocks, 64)

    # Planos de frequencia: transpoe para (64, n_blocks)
    # Cada linha = todos os valores daquela frequencia em todos os blocos
    planes = zz.T.copy()                  # (64, n_blocks)

    # DPCM no coeficiente DC (plano 0): subtrai bloco anterior
    # Blocos adjacentes na varredura raster tem DCs correlacionados
    planes[0, 1:] = (planes[0, 1:].astype(np.int32) -
                     planes[0, :-1].astype(np.int32)).astype(np.int16)

    # Estatisticas
    total_coeffs = quant.size
    zero_coeffs  = int((quant == 0).sum())
    zero_blocks  = int(np.all(quant == 0, axis=1).sum())
    stats = {
        'total_blocks':     n_blocks,
        'zero_blocks':      zero_blocks,
        'predicted_blocks': n_blocks - 1,
        'sparsity':         zero_coeffs / total_coeffs * 100.0 if total_coeffs > 0 else 0.0,
        'avg_energy':       float(np.mean(quant.astype(np.float64) ** 2)),
    }

    data = n_blocks.to_bytes(4, 'little') + planes.astype(np.int16).tobytes()
    return data, stats


def _decompress_channel_v4(data: bytes, width: int, height: int,
                            quant_table: np.ndarray) -> np.ndarray:
    """Descomprime canal lossy v4 (planos de frequencia + DPCM DC)."""
    bh = (height + 7) // 8
    bw = (width + 7) // 8
    ph, pw = bh * 8, bw * 8
    n_stored = int.from_bytes(data[0:4], 'little')

    # Ler planos de frequencia: (64, n_blocks)
    raw = np.frombuffer(data[4:4 + n_stored * 64 * 2], dtype=np.int16)
    planes = raw.reshape(64, n_stored).copy()

    # Desfazer DPCM no plano DC
    planes[0] = np.cumsum(planes[0].astype(np.int32)).astype(np.int16)

    # Transpor de volta para (n_blocks, 64) em ordem zigzag
    zz = planes.T                          # (n_stored, 64)

    # Desfazer zigzag: reconstruir ordem row-major
    quant = np.zeros((n_stored, 64), dtype=np.int16)
    quant[:, ZIGZAG_IDX] = zz             # quant[b, row_major_pos] = zz[b, zigzag_pos]

    # Dequantizacao
    qflat = quant_table.flatten()
    dct = quant.astype(np.float64) * qflat   # (n_blocks, 64)

    # IDCT 2D vetorizado: D^T @ dct_block @ D
    dct_3d = dct.reshape(n_stored, 8, 8)
    blocks  = (_DCT_MT @ dct_3d) @ _DCT_M   # (n_blocks, 8, 8)

    # Reconstruir imagem padded
    padded = np.clip(blocks + 128.0, 0.0, 255.0)
    padded = (padded.reshape(bh, bw, 8, 8)
                    .transpose(0, 2, 1, 3)
                    .reshape(ph, pw))

    return padded[:height, :width]


def _compress_lossless_v4(channel: np.ndarray) -> bytes:
    """
    Comprime canal lossless v4: DPCM horizontal pixel a pixel.

    Formato: H*W valores int16 em varredura raster.
    O pixel [r,c] armazena channel[r,c] - channel[r,c-1] (ou channel[r,0] na primeira coluna).
    Sem overhead de blocos. O zlib final faz a codificacao de entropia.
    """
    h, w = channel.shape
    ch32 = channel.astype(np.int32)
    dpcm = np.empty((h, w), dtype=np.int16)
    dpcm[:, 0] = ch32[:, 0]
    dpcm[:, 1:] = (ch32[:, 1:] - ch32[:, :-1]).astype(np.int16)
    return dpcm.tobytes()


def _decompress_lossless_v4(data: bytes, height: int, width: int) -> np.ndarray:
    """Descomprime canal lossless v4 (DPCM horizontal)."""
    dpcm = np.frombuffer(data, dtype=np.int16).reshape(height, width).astype(np.int32)
    return np.cumsum(dpcm, axis=1).astype(np.int16)


# ==============================================================
# Implementacao Python pura (fallback quando motor C indisponivel)
# ==============================================================

def _make_dct_matrix():
    D = np.zeros((8, 8))
    for i in range(8):
        for j in range(8):
            if i == 0:
                D[i, j] = 1.0 / np.sqrt(8.0)
            else:
                D[i, j] = np.sqrt(2.0 / 8.0) * np.cos((2 * j + 1) * i * np.pi / 16.0)
    return D

_DCT_M  = _make_dct_matrix()
_DCT_MT = _DCT_M.T


def _dct8x8_py(block):
    M = block.reshape(8, 8)
    return (_DCT_M @ M @ _DCT_MT).flatten()


def _idct8x8_py(block):
    M = block.reshape(8, 8)
    return (_DCT_MT @ M @ _DCT_M).flatten()


def _spiral_order_py(img_width, img_height):
    """Gera ordem espiral Middle-Out identica ao motor C."""
    bw = (img_width + 7) // 8
    bh = (img_height + 7) // 8
    total = bw * bh
    visited = [False] * (bw * bh)
    dr = [0, 1, 0, -1]
    dc = [1, 0, -1, 0]
    rows, cols = [], []
    r, c = bh // 2, bw // 2
    direction = 0
    steps = 1
    step_count = 0
    turns = 0
    if 0 <= r < bh and 0 <= c < bw:
        rows.append(r); cols.append(c)
        visited[r * bw + c] = True
    while len(rows) < total:
        r += dr[direction]
        c += dc[direction]
        step_count += 1
        if 0 <= r < bh and 0 <= c < bw and not visited[r * bw + c]:
            rows.append(r); cols.append(c)
            visited[r * bw + c] = True
        if step_count >= steps:
            step_count = 0
            direction = (direction + 1) % 4
            turns += 1
            if turns % 2 == 0:
                steps += 1
        if r < -bh or r >= 2 * bh or c < -bw or c >= 2 * bw:
            for i in range(bh):
                for j in range(bw):
                    if not visited[i * bw + j]:
                        rows.append(i); cols.append(j)
                        visited[i * bw + j] = True
            break
    return rows, cols


def _rle_encode_py(data):
    """Codifica array int16 com RLE identico ao motor C."""
    out = bytearray()
    zeros = 0
    for v in data:
        v = int(v)
        if v == 0:
            zeros += 1
            if zeros == 255:
                out += b'\xff\x00\x00'
                zeros = 0
        else:
            out += bytes([zeros & 0xFF, v & 0xFF, (v >> 8) & 0xFF])
            zeros = 0
    out += b'\xff\x00\x00'
    return bytes(out)


def _rle_decode_py(data, length=64):
    """Decodifica RLE identico ao motor C."""
    out = np.zeros(length, dtype=np.int16)
    out_pos = 0
    in_pos = 0
    while in_pos + 2 < len(data) and out_pos < length:
        skip = data[in_pos]
        val = int.from_bytes(bytes(data[in_pos + 1:in_pos + 3]),
                             byteorder='little', signed=True)
        in_pos += 3
        if skip == 0xFF and val == 0:
            break
        for _ in range(skip):
            if out_pos < length:
                out_pos += 1
        if not (skip == 255 and val == 0):
            if out_pos < length:
                out[out_pos] = val
                out_pos += 1
    return out


def _adaptive_quant_factor_py(block, quality):
    variance = float(np.var(block))
    norm_var = variance / (255.0 * 255.0)
    factor = 1.0 - 0.5 * (norm_var / (norm_var + 0.01))
    if quality < 50:
        q_scale = 5000.0 / quality
    else:
        q_scale = 200.0 - 2.0 * quality
    q_scale /= 100.0
    return factor * q_scale


class _PyStats:
    """Substituto Python para MOStats (usado no fallback sem motor C)."""
    def __init__(self):
        self.total_blocks = 0
        self.zero_blocks = 0
        self.predicted_blocks = 0
        self.avg_energy = 0.0
        self.sparsity = 0.0


def _compress_channel_py(channel: np.ndarray, quant_table: np.ndarray,
                         quality: int) -> tuple:
    """Comprime canal usando DCT + quantizacao adaptativa Middle-Out (Python puro)."""
    h, w = channel.shape
    bw = (w + 7) // 8
    bh = (h + 7) // 8
    pw = bw * 8
    ph = bh * 8

    padded = np.zeros((ph, pw), dtype=np.float64)
    padded[:h, :w] = channel
    if w < pw:
        padded[:h, w:] = channel[:, w - 1:w]
    if h < ph:
        padded[h:, :] = padded[h - 1:h, :]

    spiral_rows, spiral_cols = _spiral_order_py(pw, ph)
    n_blocks = len(spiral_rows)
    stats = _PyStats()
    stats.total_blocks = n_blocks

    out = bytearray()
    out += n_blocks.to_bytes(4, 'little')

    qflat = quant_table.flatten()
    prev_quant = None
    total_coeffs = 0
    zero_coeffs = 0

    for b in range(n_blocks):
        py_off = spiral_rows[b] * 8
        px_off = spiral_cols[b] * 8
        block = padded[py_off:py_off + 8, px_off:px_off + 8].flatten() - 128.0

        adapt = _adaptive_quant_factor_py(block, quality)
        dct_block = _dct8x8_py(block)
        qf = np.maximum(qflat * adapt, 1.0)
        curr_quant = np.round(dct_block / qf).astype(np.int16)

        if prev_quant is not None:
            delta = (curr_quant.astype(np.int32) - prev_quant.astype(np.int32)).astype(np.int16)
            e_orig  = int(np.sum(curr_quant.astype(np.int32) ** 2))
            e_delta = int(np.sum(delta.astype(np.int32) ** 2))
            if e_delta < e_orig * 8 // 10:
                encoded = delta
                used_delta = 1
            else:
                encoded = curr_quant.copy()
                used_delta = 0
        else:
            encoded = curr_quant.copy()
            used_delta = 0

        adapt_byte = min(255, int(adapt * 25.5))
        rle_data = _rle_encode_py(encoded)
        out += bytes([used_delta, adapt_byte])
        out += len(rle_data).to_bytes(2, 'little')
        out += rle_data

        zero_coeffs += int(np.sum(curr_quant == 0))
        total_coeffs += 64
        if int(np.all(curr_quant == 0)):
            stats.zero_blocks += 1
        if used_delta:
            stats.predicted_blocks += 1
        stats.avg_energy += float(np.sum(curr_quant.astype(np.float64) ** 2))
        prev_quant = curr_quant.copy()

    if n_blocks > 0:
        stats.avg_energy /= n_blocks
        stats.sparsity = (zero_coeffs / total_coeffs * 100.0) if total_coeffs > 0 else 0.0

    return bytes(out), stats


def _decompress_channel_py(data: bytes, width: int, height: int,
                           quant_table: np.ndarray, quality: int) -> np.ndarray:
    """Descomprime canal usando IDCT + dequantizacao (Python puro)."""
    bw = (width + 7) // 8
    bh = (height + 7) // 8
    pw = bw * 8
    ph = bh * 8
    padded = np.zeros((ph, pw), dtype=np.float64)

    n_blocks = int.from_bytes(data[0:4], 'little')
    in_pos = 4
    spiral_rows, spiral_cols = _spiral_order_py(pw, ph)
    qflat = quant_table.flatten()
    prev_quant = None

    for b in range(min(n_blocks, len(spiral_rows))):
        if in_pos + 4 > len(data):
            break
        py_off = spiral_rows[b] * 8
        px_off = spiral_cols[b] * 8

        used_delta = data[in_pos]; in_pos += 1
        adapt_byte = data[in_pos]; in_pos += 1
        adapt = adapt_byte / 25.5
        rle_size = int.from_bytes(data[in_pos:in_pos + 2], 'little'); in_pos += 2

        decoded_rle = _rle_decode_py(data[in_pos:in_pos + rle_size])
        in_pos += rle_size

        if used_delta and prev_quant is not None:
            curr_quant = (decoded_rle.astype(np.int32) + prev_quant.astype(np.int32)).astype(np.int16)
        else:
            curr_quant = decoded_rle.copy()

        qf = np.maximum(qflat * adapt, 1.0)
        dct_block = curr_quant.astype(np.float64) * qf
        block = _idct8x8_py(dct_block)
        padded[py_off:py_off + 8, px_off:px_off + 8] = np.clip(
            block.reshape(8, 8) + 128.0, 0, 255)
        prev_quant = curr_quant.copy()

    return padded[:height, :width]


def _compress_lossless_channel_py(channel: np.ndarray) -> tuple:
    """Comprime canal int16 usando DPCM Middle-Out lossless (Python puro)."""
    h, w = channel.shape
    bw = (w + 7) // 8
    bh = (h + 7) // 8
    pw = bw * 8
    ph = bh * 8

    padded = np.zeros((ph, pw), dtype=np.int16)
    padded[:h, :w] = channel
    if w < pw:
        padded[:h, w:] = channel[:, w - 1:w]
    if h < ph:
        padded[h:, :] = padded[h - 1:h, :]

    spiral_rows, spiral_cols = _spiral_order_py(pw, ph)
    n_blocks = len(spiral_rows)
    stats = _PyStats()
    stats.total_blocks = n_blocks

    out = bytearray()
    out += n_blocks.to_bytes(4, 'little')
    out += pw.to_bytes(2, 'little')
    out += ph.to_bytes(2, 'little')

    prev_block = None
    total_res = 0
    zero_res = 0

    for b in range(n_blocks):
        py_off = spiral_rows[b] * 8
        px_off = spiral_cols[b] * 8
        curr = padded[py_off:py_off + 8, px_off:px_off + 8].flatten().astype(np.int16)

        if prev_block is not None:
            delta = (curr.astype(np.int32) - prev_block.astype(np.int32)).astype(np.int16)
            e_raw   = int(np.sum(curr.astype(np.int32) ** 2))
            e_delta = int(np.sum(delta.astype(np.int32) ** 2))
            if e_delta <= e_raw * 9 // 10:
                residuals = delta
                used_delta = 1
            else:
                residuals = curr.copy()
                used_delta = 0
        else:
            residuals = curr.copy()
            used_delta = 0

        zero_res += int(np.sum(residuals == 0))
        total_res += 64
        if used_delta:
            stats.predicted_blocks += 1

        rle_data = _rle_encode_py(residuals)
        out += bytes([used_delta])
        out += len(rle_data).to_bytes(2, 'little')
        out += rle_data
        prev_block = curr.copy()

    stats.sparsity = (zero_res / total_res * 100.0) if total_res > 0 else 0.0
    return bytes(out), stats


def _decompress_lossless_channel_py(data: bytes, width: int,
                                     height: int) -> np.ndarray:
    """Descomprime canal lossless (Python puro)."""
    bw = (width + 7) // 8
    bh = (height + 7) // 8
    pw = bw * 8
    ph = bh * 8

    n_blocks = int.from_bytes(data[0:4], 'little')
    padded = np.zeros((ph, pw), dtype=np.int16)
    spiral_rows, spiral_cols = _spiral_order_py(pw, ph)
    prev_block = None
    in_pos = 8

    for b in range(min(n_blocks, len(spiral_rows))):
        if in_pos + 3 > len(data):
            break
        py_off = spiral_rows[b] * 8
        px_off = spiral_cols[b] * 8

        used_delta = data[in_pos]; in_pos += 1
        rle_size = int.from_bytes(data[in_pos:in_pos + 2], 'little'); in_pos += 2

        residuals = _rle_decode_py(data[in_pos:in_pos + rle_size])
        in_pos += rle_size

        if used_delta and prev_block is not None:
            curr = (residuals.astype(np.int32) + prev_block.astype(np.int32)).astype(np.int16)
        else:
            curr = residuals.copy()

        padded[py_off:py_off + 8, px_off:px_off + 8] = curr.reshape(8, 8)
        prev_block = curr.copy()

    return padded[:height, :width]


# ==============================================================
# Pipeline Middle-Out Lossless (C engine)
# ==============================================================

def _compress_lossless_channel_c(channel: np.ndarray) -> tuple:
    """
    Comprime canal int16 usando Middle-Out DPCM lossless.
    Usa motor C se disponivel, senao fallback Python puro.
    """
    lib = _load_engine()
    if not lib:
        return _compress_lossless_channel_py(channel)

    flat = np.ascontiguousarray(channel.flatten(), dtype=np.int16)
    h, w = channel.shape
    size_out = c_int(0)
    stats = MOStats()

    ptr = lib.mo_compress_lossless_ch(
        flat.ctypes.data_as(c_int16_p),
        c_int(w), c_int(h),
        ctypes.byref(size_out),
        ctypes.byref(stats),
    )

    if not ptr or size_out.value <= 0:
        return _compress_lossless_channel_py(channel)

    data = bytes(ctypes.string_at(ptr, size_out.value))
    _LIBC.free(ptr)
    return data, stats


def _decompress_lossless_channel_c(data: bytes, width: int,
                                    height: int) -> np.ndarray:
    """
    Descomprime canal lossless.
    Usa motor C se disponivel, senao fallback Python puro.
    """
    lib = _load_engine()
    if not lib:
        return _decompress_lossless_channel_py(data, width, height)

    buf = (c_uint8 * len(data)).from_buffer_copy(data)

    ptr = lib.mo_decompress_lossless_ch(
        buf, c_int(len(data)),
        c_int(width), c_int(height),
    )

    if not ptr:
        return _decompress_lossless_channel_py(data, width, height)

    int16_ptr = ctypes.cast(ptr, POINTER(c_int16))
    arr = np.ctypeslib.as_array(int16_ptr, shape=(height, width)).copy()
    _LIBC.free(ptr)
    return arr


# ==============================================================
# Pipeline Middle-Out (C engine) - LOSSY
# ==============================================================

def _compress_channel_c(channel: np.ndarray, quant_table: np.ndarray,
                        quality: int) -> bytes:
    """Comprime canal usando motor C, ou fallback Python puro."""
    lib = _load_engine()
    if not lib:
        return _compress_channel_py(channel, quant_table, quality)

    h, w = channel.shape
    flat = np.ascontiguousarray(channel.flatten(), dtype=np.float64)
    qflat = np.ascontiguousarray(quant_table.flatten(), dtype=np.float64)

    size_out = c_int(0)
    stats = MOStats()

    ptr = lib.mo_compress_channel(
        flat.ctypes.data_as(POINTER(c_double)),
        c_int(w), c_int(h),
        qflat.ctypes.data_as(POINTER(c_double)),
        c_int(quality),
        ctypes.byref(size_out),
        ctypes.byref(stats),
    )

    if not ptr or size_out.value <= 0:
        return _compress_channel_py(channel, quant_table, quality)

    data = bytes(ctypes.string_at(ptr, size_out.value))
    _LIBC.free(ptr)
    return data, stats


def _decompress_channel_c(data: bytes, width: int, height: int,
                          quant_table: np.ndarray, quality: int) -> np.ndarray:
    """Descomprime canal usando motor C, ou fallback Python puro."""
    lib = _load_engine()
    if not lib:
        return _decompress_channel_py(data, width, height, quant_table, quality)

    qflat = np.ascontiguousarray(quant_table.flatten(), dtype=np.float64)
    buf = (c_uint8 * len(data)).from_buffer_copy(data)

    ptr = lib.mo_decompress_channel(
        buf, c_int(len(data)),
        c_int(width), c_int(height),
        qflat.ctypes.data_as(POINTER(c_double)),
        c_int(quality),
    )

    if not ptr:
        return _decompress_channel_py(data, width, height, quant_table, quality)

    double_ptr = ctypes.cast(ptr, POINTER(c_double))
    arr = np.ctypeslib.as_array(double_ptr, shape=(height, width)).copy()
    _LIBC.free(ptr)
    return arr


# ==============================================================
# Leitura de imagens - suporta TODOS os formatos
# ==============================================================

SUPPORTED_FORMATS = {
    'PNG', 'JPEG', 'JPG', 'BMP', 'TIFF', 'TIF', 'GIF', 'WEBP', 'ICO',
    'TGA', 'PPM', 'PGM', 'PBM', 'PNM', 'XBM', 'XPM', 'DIB', 'EPS', 'IM',
    'PCX', 'MSP', 'SGI', 'SPIDER', 'DDS', 'FLI', 'FLC', 'FPX', 'FTEX',
    'GBR', 'GD', 'IMT', 'IPTC', 'NAA', 'MCIDAS', 'MIC', 'MPO', 'PALM',
    'PCD', 'PIXAR', 'PSD', 'WMF', 'EMF', 'WAL', 'XVTHUMB', 'APNG', 'JFIF',
    'JP2', 'JPX', 'JPF', 'J2K', 'J2C',
}


def _load_any_image(path: str) -> tuple:
    """
    Carrega imagem de qualquer formato suportado.
    Retorna (array_rgb_ou_rgba, metadata_dict).
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Arquivo nao encontrado: {path}")

    try:
        img = Image.open(path)
        img.load()
    except Exception as e:
        raise ValueError(f"Nao foi possivel abrir a imagem: {e}")

    original_format = (img.format or 'UNKNOWN').upper()
    original_mode = img.mode
    has_alpha = img.mode in ('RGBA', 'LA', 'PA') or 'transparency' in img.info

    # Lida com animacoes (GIF, APNG): usa apenas o primeiro frame
    is_animated = getattr(img, 'is_animated', False)
    n_frames = getattr(img, 'n_frames', 1)

    # Converte para RGB/RGBA
    if has_alpha:
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        arr = np.array(img)
    else:
        if img.mode != 'RGB':
            img = img.convert('RGB')
        arr = np.array(img)

    metadata = {
        'original_format': original_format,
        'original_mode': original_mode,
        'has_alpha': has_alpha,
        'is_animated': is_animated,
        'n_frames': n_frames,
    }
    return arr, metadata


# ==============================================================
# Compressao principal
# ==============================================================

def _sha256_file(path: str) -> str:
    """Calcula SHA-256 de um arquivo."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def _sha256_array(arr: np.ndarray) -> str:
    """Calcula SHA-256 de um array numpy."""
    return hashlib.sha256(np.ascontiguousarray(arr).tobytes()).hexdigest()


def compress(input_path: str, output_path: str = None,
             quality: int = 75, lossless: bool = False) -> dict:
    """
    Comprime qualquer imagem para o formato .PP

    Args:
        input_path: Caminho da imagem de entrada (qualquer formato)
        output_path: Caminho do arquivo .PP (auto-detectado se None)
        quality:   Qualidade de 1 a 100 (padrao 75, ignorado se lossless=True)
        lossless:  True = modo sem perdas (Middle-Out DPCM + RCT)

    Returns:
        Dicionario com estatisticas completas da compressao
    """
    start_time = time.time()

    if output_path is None:
        base = os.path.splitext(input_path)[0]
        output_path = base + PP_EXTENSION

    _load_engine()  # tenta carregar motor C; se falhar, usa fallback Python

    original_size = os.path.getsize(input_path)
    img_array, metadata = _load_any_image(input_path)
    height, width = img_array.shape[:2]
    has_alpha = metadata['has_alpha']

    if has_alpha:
        rgb = img_array[..., :3]
        alpha_u8 = img_array[..., 3]
    else:
        rgb = img_array
        alpha_u8 = None

    # Calcula hash do original para verificacao lossless
    original_hash = _sha256_array(img_array) if lossless else ''

    if lossless:
        # ============================================================
        # Pipeline Lossless v5: Multi-estrategia sem perdas
        # Tenta 3 abordagens e escolhe a menor — sempre pixel-perfeito.
        #  A) stored  : bytes originais do arquivo (sem re-codificacao)
        #  B) png     : PNG em memoria via PIL (RFC 2083, deflate otimizado)
        #  C) dpcm    : RCT + DPCM horizontal + zlib nivel 9
        # ============================================================
        import io as _io

        # --- Estrategia A: bytes originais ---
        with open(input_path, 'rb') as _fin:
            _orig_bytes = _fin.read()
        size_stored = len(_orig_bytes)

        # --- Estrategia B: PNG em memoria ---
        _buf = _io.BytesIO()
        _pil = Image.fromarray(img_array, 'RGBA' if has_alpha else 'RGB')
        _pil.save(_buf, format='PNG', optimize=True, compress_level=9)
        _png_bytes = _buf.getvalue()
        size_png = len(_png_bytes)

        # --- Estrategia C: RCT + DPCM + zlib ---
        y_ch, cb_ch, cr_ch = _rct_forward(rgb)
        y_data  = _compress_lossless_v4(y_ch)
        cb_data = _compress_lossless_v4(cb_ch)
        cr_data = _compress_lossless_v4(cr_ch)
        alpha_data = None
        if has_alpha:
            alpha_ch = alpha_u8.astype(np.int16)
            alpha_data = _compress_lossless_v4(alpha_ch)
        _dpcm_raw = y_data + cb_data + cr_data + (alpha_data if alpha_data else b'')
        _dpcm_cmp = zlib.compress(_dpcm_raw, level=9)
        size_dpcm = len(_dpcm_cmp)

        # --- Escolhe a menor estrategia ---
        best = min(size_stored, size_png, size_dpcm)
        if size_stored == best:
            lossless_strategy = 'stored'
        elif size_png == best:
            lossless_strategy = 'png'
        else:
            lossless_strategy = 'dpcm'

        _ll_header = {
            'version': PP_VERSION,
            'codec': 4,
            'lossless': True,
            'lossless_strategy': lossless_strategy,
            'width': int(width),
            'height': int(height),
            'quality': 100,
            'has_alpha': bool(has_alpha),
            'original_format': metadata['original_format'],
            'original_mode': metadata['original_mode'],
            'original_hash': original_hash,
        }
        if lossless_strategy == 'dpcm':
            _ll_header.update({
                'y_size':     len(y_data),
                'cb_size':    len(cb_data),
                'cr_size':    len(cr_data),
                'alpha_size': len(alpha_data) if alpha_data else 0,
            })

        if lossless_strategy == 'stored':
            _ll_payload = _orig_bytes
        elif lossless_strategy == 'png':
            _ll_payload = _png_bytes
        else:
            _ll_payload = _dpcm_cmp

        _ll_header_json = json.dumps(_ll_header, separators=(',', ':')).encode('utf-8')
        with open(output_path, 'wb') as _f:
            _f.write(PP_MAGIC)
            _f.write(struct.pack('<H', PP_VERSION))
            _f.write(struct.pack('<I', len(_ll_header_json)))
            _f.write(_ll_header_json)
            _f.write(struct.pack('<I', len(_ll_payload)))
            _f.write(_ll_payload)

        elapsed      = time.time() - start_time
        output_size  = os.path.getsize(output_path)
        total_pixels = width * height
        ratio        = original_size / output_size if output_size > 0 else 0
        reduction    = (1 - output_size / original_size) * 100 if original_size > 0 else 0

        _strategy_labels = {
            'stored': 'Bytes originais (sem re-codificacao)',
            'png':    'PNG pixel-perfeito (deflate otimizado)',
            'dpcm':   'RCT + DPCM espiral + zlib',
        }
        return {
            'input_file':              input_path,
            'output_file':             output_path,
            'original_format':         metadata['original_format'],
            'original_mode':           metadata['original_mode'],
            'lossless':                True,
            'lossless_strategy':       lossless_strategy,
            'lossless_strategy_label': _strategy_labels[lossless_strategy],
            'width':                   width,
            'height':                  height,
            'total_pixels':            total_pixels,
            'megapixels':              round(total_pixels / 1_000_000, 3),
            'has_alpha':               has_alpha,
            'original_size':           original_size,
            'compressed_size':         output_size,
            'compression_ratio':       round(ratio, 2),
            'reduction_percent':       round(reduction, 2),
            'quality':                 100,
            'time_seconds':            round(elapsed, 3),
            'pixels_per_second':       int(total_pixels / elapsed) if elapsed > 0 else 0,
            'total_blocks':            0,
            'predicted_blocks':        0,
            'prediction_percent':      0.0,
            'coefficient_sparsity':    0.0,
            'bits_per_pixel':          round(output_size * 8 / total_pixels, 3),
            'original_hash':           original_hash,
            'psnr':                    float('inf'),
            'psnr_str':                'LOSSLESS (perfeito)',
            'zero_blocks':             0,
            'zero_blocks_percent':     0.0,
        }

    else:
        # ============================================================
        # Pipeline Lossy v4: DCT vetorizado + zigzag + planos de frequencia
        # Elimina overhead por bloco; zlib explora correlacao entre blocos.
        #
        # Formatos ja comprimidos com codec lossy (JPEG, WebP…) sao armazenados
        # diretamente no container .PP sem re-aplicar DCT. Isso evita dupla
        # compressao lossy que degradaria qualidade sem reducao de tamanho.
        # O zlib (DEFLATE) e aplicado como segunda etapa de entropia — esse
        # dois estagios (DCT+DEFLATE) sao equivalentes ao pipeline JPEG
        # (DCT+Huffman) e nao constituem "dupla compressao" no sentido negativo.
        # ============================================================
        _PRECOMPRESSED_FMTS = {'JPEG', 'JPG', 'WEBP', 'HEIC', 'HEIF'}
        if metadata['original_format'].upper() in _PRECOMPRESSED_FMTS:
            # Formato ja e DCT-lossy: armazena bytes originais no container PP
            # para preservar qualidade original sem re-codificacao.
            with open(input_path, 'rb') as _fin:
                _orig_bytes = _fin.read()
            _stored_hdr = {
                'version': PP_VERSION, 'codec': 4, 'stored': True,
                'lossless': False,
                'width': int(width), 'height': int(height),
                'quality': int(quality), 'has_alpha': bool(has_alpha),
                'original_format': metadata['original_format'],
                'original_mode':   metadata['original_mode'],
                'y_size': 0, 'cb_size': 0, 'cr_size': 0, 'alpha_size': 0,
            }
            _stored_hdr_json = json.dumps(_stored_hdr, separators=(',', ':')).encode('utf-8')
            with open(output_path, 'wb') as _f:
                _f.write(PP_MAGIC)
                _f.write(struct.pack('<H', PP_VERSION))
                _f.write(struct.pack('<I', len(_stored_hdr_json)))
                _f.write(_stored_hdr_json)
                _f.write(struct.pack('<I', len(_orig_bytes)))
                _f.write(_orig_bytes)
            elapsed      = time.time() - start_time
            output_size  = os.path.getsize(output_path)
            total_pixels = width * height
            ratio        = original_size / output_size if output_size > 0 else 0
            reduction    = (1 - output_size / original_size) * 100 if original_size > 0 else 0
            return {
                'input_file':            input_path,
                'output_file':           output_path,
                'original_format':       metadata['original_format'],
                'original_mode':         metadata['original_mode'],
                'lossless':              False,
                'lossless_strategy':     'stored',
                'lossless_strategy_label': 'Bytes originais (sem re-codificacao DCT)',
                'width':                 width,
                'height':                height,
                'total_pixels':          total_pixels,
                'megapixels':            round(total_pixels / 1_000_000, 3),
                'has_alpha':             has_alpha,
                'original_size':         original_size,
                'compressed_size':       output_size,
                'compression_ratio':     round(ratio, 2),
                'reduction_percent':     round(reduction, 2),
                'quality':               quality,
                'time_seconds':          round(elapsed, 3),
                'pixels_per_second':     int(total_pixels / elapsed) if elapsed > 0 else 0,
                'total_blocks':          0,
                'predicted_blocks':      0,
                'prediction_percent':    0.0,
                'coefficient_sparsity':  0.0,
                'bits_per_pixel':        round(output_size * 8 / total_pixels, 3),
                'original_hash':         '',
                'psnr':                  float('inf'),
                'psnr_str':              'ARMAZENADO (sem re-codificacao)',
                'zero_blocks':           0,
                'zero_blocks_percent':   0.0,
            }

        ycbcr = _rgb_to_ycbcr(rgb)
        y_channel  = ycbcr[..., 0]
        cb_channel = ycbcr[..., 1]
        cr_channel = ycbcr[..., 2]

        cb_sub = _subsample_420(cb_channel)
        cr_sub = _subsample_420(cr_channel)

        quant_y = _get_quant_table(QUANT_LUMINANCE,   quality)
        quant_c = _get_quant_table(QUANT_CHROMINANCE,  quality)

        y_data,  y_stats  = _compress_channel_v4(y_channel, quant_y)
        cb_data, cb_stats = _compress_channel_v4(cb_sub,    quant_c)
        cr_data, cr_stats = _compress_channel_v4(cr_sub,    quant_c)

        alpha_data = None
        if has_alpha:
            quant_a = _get_quant_table(QUANT_LUMINANCE, max(quality, 90))
            alpha_data, _ = _compress_channel_v4(
                alpha_u8.astype(np.float64), quant_a)

        header = {
            'version': PP_VERSION,
            'codec': 4,
            'lossless': False,
            'width': int(width),
            'height': int(height),
            'quality': int(quality),
            'has_alpha': bool(has_alpha),
            'original_format': metadata['original_format'],
            'original_mode': metadata['original_mode'],
            'cb_shape': list(cb_sub.shape),
            'cr_shape': list(cr_sub.shape),
            'y_size':    len(y_data),
            'cb_size':   len(cb_data),
            'cr_size':   len(cr_data),
            'alpha_size': len(alpha_data) if alpha_data else 0,
        }

        all_data = y_data + cb_data + cr_data
        if alpha_data:
            all_data += alpha_data

        total_blocks = (y_stats['total_blocks'] + cb_stats['total_blocks'] +
                        cr_stats['total_blocks'])
        predicted    = (y_stats['predicted_blocks'] + cb_stats['predicted_blocks'] +
                        cr_stats['predicted_blocks'])
        avg_sparsity = (y_stats['sparsity'] + cb_stats['sparsity'] +
                        cr_stats['sparsity']) / 3
        zero_blocks  = (y_stats['zero_blocks'] + cb_stats['zero_blocks'] +
                        cr_stats['zero_blocks'])

    header_json      = json.dumps(header, separators=(',', ':')).encode('utf-8')
    final_compressed = zlib.compress(all_data, level=9)

    # Overhead fixo do contêiner .PP
    pp_overhead = 4 + 2 + 4 + len(header_json) + 4  # magic+ver+hdr_size+hdr+data_size

    if pp_overhead + len(final_compressed) >= original_size:
        # Modo armazenado: compressao nao reduziu o tamanho.
        # Guarda os bytes originais diretamente no container .PP.
        with open(input_path, 'rb') as _fin:
            _orig_bytes = _fin.read()
        stored_header = {
            'version': PP_VERSION,
            'codec': 4,
            'stored': True,
            'lossless': lossless,
            'width': int(width),
            'height': int(height),
            'quality': 100 if lossless else int(quality),
            'has_alpha': bool(has_alpha),
            'original_format': metadata['original_format'],
            'original_mode':   metadata['original_mode'],
            'y_size': 0, 'cb_size': 0, 'cr_size': 0, 'alpha_size': 0,
        }
        header_json = json.dumps(stored_header, separators=(',', ':')).encode('utf-8')
        payload     = _orig_bytes        # ja comprimido (JPEG/PNG) ou pequeno o suficiente
        with open(output_path, 'wb') as f:
            f.write(PP_MAGIC)
            f.write(struct.pack('<H', PP_VERSION))
            f.write(struct.pack('<I', len(header_json)))
            f.write(header_json)
            f.write(struct.pack('<I', len(payload)))
            f.write(payload)
    else:
        with open(output_path, 'wb') as f:
            f.write(PP_MAGIC)
            f.write(struct.pack('<H', PP_VERSION))
            f.write(struct.pack('<I', len(header_json)))
            f.write(header_json)
            f.write(struct.pack('<I', len(final_compressed)))
            f.write(final_compressed)

    elapsed = time.time() - start_time
    output_size = os.path.getsize(output_path)
    total_pixels = width * height

    ratio     = original_size / output_size if output_size > 0 else 0
    reduction = (1 - output_size / original_size) * 100 if original_size > 0 else 0
    pred_pct  = (predicted / total_blocks * 100) if total_blocks > 0 else 0

    result = {
        'input_file': input_path,
        'output_file': output_path,
        'original_format': metadata['original_format'],
        'original_mode':   metadata['original_mode'],
        'lossless': lossless,
        'width': width,
        'height': height,
        'total_pixels': total_pixels,
        'megapixels': round(total_pixels / 1_000_000, 3),
        'has_alpha': has_alpha,
        'original_size':    original_size,
        'compressed_size':  output_size,
        'compression_ratio': round(ratio, 2),
        'reduction_percent': round(reduction, 2),
        'quality': 100 if lossless else quality,
        'time_seconds':      round(elapsed, 3),
        'pixels_per_second': int(total_pixels / elapsed) if elapsed > 0 else 0,
        'total_blocks':      int(total_blocks),
        'predicted_blocks':  int(predicted),
        'prediction_percent': round(pred_pct, 2),
        'coefficient_sparsity': round(avg_sparsity, 2),
        'bits_per_pixel':    round(output_size * 8 / total_pixels, 3),
        'original_hash': original_hash,
    }

    if lossless:
        result['psnr'] = float('inf')
        result['psnr_str'] = 'LOSSLESS (perfeito)'
        result['zero_blocks'] = 0
        result['zero_blocks_percent'] = 0.0
    else:
        result['zero_blocks'] = int(zero_blocks)
        result['zero_blocks_percent'] = round(
            (zero_blocks / total_blocks * 100) if total_blocks > 0 else 0, 2)
        result['psnr'] = None
        result['psnr_str'] = 'N/A (use pp d para calcular)'

    return result


# ==============================================================
# Descompressao principal
# ==============================================================

def decompress(input_path: str, output_path: str = None) -> dict:
    """
    Descomprime um arquivo .PP de volta para imagem.

    Args:
        input_path: Caminho do arquivo .PP
        output_path: Caminho da imagem de saida (auto-detectado se None)

    Returns:
        Dicionario com estatisticas da descompressao (inclui PSNR e verificacao)
    """
    import io as _io

    start_time = time.time()

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Arquivo nao encontrado: {input_path}")

    _load_engine()  # tenta carregar motor C; se falhar, usa fallback Python

    with open(input_path, 'rb') as f:
        magic = f.read(4)
        if magic != PP_MAGIC:
            raise ValueError(
                f"Arquivo invalido: nao e um arquivo .PP "
                f"(esperado {PP_MAGIC!r}, recebido {magic!r})"
            )
        version = struct.unpack('<H', f.read(2))[0]
        if version > PP_VERSION:
            raise ValueError(
                f"Versao {version} nao suportada (max: {PP_VERSION})"
            )
        header_size = struct.unpack('<I', f.read(4))[0]
        header = json.loads(f.read(header_size).decode('utf-8'))
        data_size = struct.unpack('<I', f.read(4))[0]
        raw_payload = f.read(data_size)

    # Rejeita bundles (pastas) — usa decompress_bundle() para isso
    if header.get('bundle', False):
        raise ValueError(
            "Este arquivo e um bundle (pasta comprimida). "
            "Use 'pp d' normalmente — o CLI detecta automaticamente."
        )

    pp_file_size     = os.path.getsize(input_path)
    codec_version    = header.get('codec', 3)
    width            = header['width']
    height           = header['height']
    quality          = header['quality']
    has_alpha        = header['has_alpha']
    is_lossless      = header.get('lossless', False)
    lossless_strategy = header.get('lossless_strategy', None)

    # Mapa de extensoes para restaurar no formato original
    _fmt_ext = {
        'JPEG': '.jpg', 'JPG': '.jpg', 'PNG': '.png', 'BMP': '.bmp',
        'TIFF': '.tif', 'TIF': '.tif', 'WEBP': '.webp', 'GIF': '.gif',
        'ICO': '.ico', 'TGA': '.tga',
    }

    # ------------------------------------------------------------------
    # Determina output_path APOS ler o header (para usar formato original)
    # ------------------------------------------------------------------
    if output_path is None:
        base = os.path.splitext(input_path)[0]
        if lossless_strategy == 'stored':
            orig_fmt = header.get('original_format', 'PNG').upper()
            ext = _fmt_ext.get(orig_fmt, '.png')
            output_path = base + '_restored' + ext
        else:
            # Lossy e lossless DPCM: sempre PNG.
            # PNG usa DEFLATE (lossless), evitando aplicar compressao lossy
            # adicional sobre pixels ja processados pelo codec.
            output_path = base + '_restored.png'

    # ------------------------------------------------------------------
    # Estrategias lossless: stored e png (payload NAO e zlib)
    # ------------------------------------------------------------------
    if lossless_strategy in ('stored', 'png') or (
            header.get('stored', False) and is_lossless):
        # Para 'stored': gravamos os bytes originais diretamente para evitar
        # re-codificacao lossy (ex.: JPEG salvo como JPEG ficaria diferente).
        # Para 'png': PIL le o PNG diretamente da memoria.
        _img_obj = Image.open(_io.BytesIO(raw_payload))
        _img_obj.load()
        _restored_arr = np.array(_img_obj)

        out_ext = os.path.splitext(output_path)[1].lower()
        orig_fmt_up = header.get('original_format', 'PNG').upper()
        stored_ext  = _fmt_ext.get(orig_fmt_up, '.png')

        if lossless_strategy == 'stored' and out_ext == stored_ext:
            # Escrita direta: sem re-codificacao (pixel-perfeito garantido)
            with open(output_path, 'wb') as _fw:
                _fw.write(raw_payload)
        else:
            _img_obj.save(output_path)

        restored_hash  = _sha256_array(_restored_arr)
        original_hash  = header.get('original_hash', '')
        verified       = (original_hash == restored_hash) if original_hash else None

        elapsed       = time.time() - start_time
        restored_size = os.path.getsize(output_path)
        return {
            'input_file':       input_path,
            'output_file':      output_path,
            'original_format':  header.get('original_format', 'UNKNOWN'),
            'lossless':         True,
            'lossless_strategy': lossless_strategy or 'stored',
            'width':            width,
            'height':           height,
            'total_pixels':     width * height,
            'megapixels':       round(width * height / 1_000_000, 3),
            'has_alpha':        has_alpha,
            'pp_size':          pp_file_size,
            'restored_size':    restored_size,
            'quality':          100,
            'psnr':             float('inf'),
            'psnr_str':         'LOSSLESS (perfeito)',
            'integrity_verified': verified,
            'original_hash':    original_hash,
            'restored_hash':    restored_hash,
            'time_seconds':     round(elapsed, 3),
            'pixels_per_second': int(width * height / elapsed) if elapsed > 0 else 0,
        }

    # ------------------------------------------------------------------
    # Modo armazenado legado (lossy que nao comprimiu bem)
    # ------------------------------------------------------------------
    if header.get('stored', False):
        _img_obj = Image.open(_io.BytesIO(raw_payload))
        _img_obj.load()
        _img_obj.save(output_path)
        elapsed = time.time() - start_time
        restored_size = os.path.getsize(output_path)
        return {
            'input_file':      input_path,
            'output_file':     output_path,
            'original_format': header.get('original_format', 'UNKNOWN'),
            'lossless':        is_lossless,
            'width':           width,
            'height':          height,
            'total_pixels':    width * height,
            'megapixels':      round(width * height / 1_000_000, 3),
            'has_alpha':       has_alpha,
            'pp_size':         pp_file_size,
            'restored_size':   restored_size,
            'quality':         quality,
            'psnr':            None,
            'psnr_str':        'N/A (modo armazenado)',
            'integrity_verified': None,
            'time_seconds':    round(elapsed, 3),
            'pixels_per_second': int(width * height / elapsed) if elapsed > 0 else 0,
        }

    # ------------------------------------------------------------------
    # Payload comprimido com zlib (lossless DPCM ou lossy DCT)
    # ------------------------------------------------------------------
    all_data = zlib.decompress(raw_payload)

    if is_lossless:
        # ============================================================
        # Descompressao Lossless DPCM (v4 numpy ou v3 motor C)
        # ============================================================
        y_size     = header['y_size']
        cb_size    = header['cb_size']
        cr_size    = header['cr_size']
        alpha_size = header.get('alpha_size', 0)

        offset  = 0
        y_data  = all_data[offset:offset + y_size];   offset += y_size
        cb_data = all_data[offset:offset + cb_size];  offset += cb_size
        cr_data = all_data[offset:offset + cr_size];  offset += cr_size
        alpha_data = all_data[offset:offset + alpha_size] if alpha_size > 0 else None

        if codec_version >= 4:
            y_ch  = _decompress_lossless_v4(y_data,  height, width)
            cb_ch = _decompress_lossless_v4(cb_data, height, width)
            cr_ch = _decompress_lossless_v4(cr_data, height, width)
        else:
            y_ch  = _decompress_lossless_channel_c(y_data,  width, height)
            cb_ch = _decompress_lossless_channel_c(cb_data, width, height)
            cr_ch = _decompress_lossless_channel_c(cr_data, width, height)

        rgb = _rct_inverse(y_ch, cb_ch, cr_ch)

        if has_alpha and alpha_data:
            if codec_version >= 4:
                alpha_ch = _decompress_lossless_v4(alpha_data, height, width)
            else:
                alpha_ch = _decompress_lossless_channel_c(alpha_data, width, height)
            alpha = np.clip(alpha_ch, 0, 255).astype(np.uint8)
            img   = Image.fromarray(np.dstack([rgb, alpha]), 'RGBA')
            restored_array = np.dstack([rgb, alpha])
        else:
            img = Image.fromarray(rgb, 'RGB')
            restored_array = rgb

        img.save(output_path, compress_level=9, optimize=True)

        restored_hash = _sha256_array(restored_array)
        original_hash = header.get('original_hash', '')
        verified = (original_hash == restored_hash) if original_hash else None

        elapsed = time.time() - start_time
        restored_size = os.path.getsize(output_path)

        return {
            'input_file':       input_path,
            'output_file':      output_path,
            'original_format':  header.get('original_format', 'UNKNOWN'),
            'lossless':         True,
            'lossless_strategy': 'dpcm',
            'width':            width,
            'height':           height,
            'total_pixels':     width * height,
            'megapixels':       round(width * height / 1_000_000, 3),
            'has_alpha':        has_alpha,
            'pp_size':          pp_file_size,
            'restored_size':    restored_size,
            'quality':          100,
            'psnr':             float('inf'),
            'psnr_str':         'LOSSLESS (perfeito)',
            'integrity_verified': verified,
            'original_hash':    original_hash,
            'restored_hash':    restored_hash,
            'time_seconds':     round(elapsed, 3),
            'pixels_per_second': int(width * height / elapsed) if elapsed > 0 else 0,
        }

    else:
        # ============================================================
        # Descompressao Lossy
        # ============================================================
        y_size     = header['y_size']
        cb_size    = header['cb_size']
        cr_size    = header['cr_size']
        alpha_size = header.get('alpha_size', 0)

        offset   = 0
        y_data   = all_data[offset:offset + y_size];   offset += y_size
        cb_data  = all_data[offset:offset + cb_size];  offset += cb_size
        cr_data  = all_data[offset:offset + cr_size];  offset += cr_size
        alpha_data = all_data[offset:offset + alpha_size] if alpha_size > 0 else None

        quant_y = _get_quant_table(QUANT_LUMINANCE,  quality)
        quant_c = _get_quant_table(QUANT_CHROMINANCE, quality)

        cb_h, cb_w = header['cb_shape']
        cr_h, cr_w = header['cr_shape']

        if codec_version >= 4:
            # v4: planos de frequencia + numpy
            y_channel = _decompress_channel_v4(y_data, width, height, quant_y)
            cb_sub    = _decompress_channel_v4(cb_data, cb_w, cb_h, quant_c)
            cr_sub    = _decompress_channel_v4(cr_data, cr_w, cr_h, quant_c)
        else:
            # v3: motor C legado (Middle-Out + RLE por bloco)
            y_channel = _decompress_channel_c(y_data, width, height, quant_y, quality)
            cb_sub    = _decompress_channel_c(cb_data, cb_w, cb_h, quant_c, quality)
            cr_sub    = _decompress_channel_c(cr_data, cr_w, cr_h, quant_c, quality)

        cb_full = _upsample_420(cb_sub, height, width)
        cr_full = _upsample_420(cr_sub, height, width)

        ycbcr = np.stack([y_channel, cb_full, cr_full], axis=-1)
        rgb   = _ycbcr_to_rgb(ycbcr)

        if has_alpha and alpha_data:
            quant_a = _get_quant_table(QUANT_LUMINANCE, max(quality, 90))
            if codec_version >= 4:
                alpha = _decompress_channel_v4(alpha_data, width, height, quant_a)
            else:
                alpha = _decompress_channel_c(alpha_data, width, height, quant_a, quality)
            alpha = np.clip(alpha, 0, 255).astype(np.uint8)
            img = Image.fromarray(np.dstack([rgb, alpha]), 'RGBA')
        else:
            img = Image.fromarray(rgb, 'RGB')

        _out_ext = os.path.splitext(output_path)[1].lower()
        if _out_ext in ('.jpg', '.jpeg'):
            # Usuario especificou saida JPEG explicitamente via -o
            if img.mode == 'RGBA':
                img = img.convert('RGB')
            img.save(output_path, quality=min(quality + 5, 95), subsampling=0)
        else:
            # Padrao PNG: usa DEFLATE (lossless) para preservar exatamente
            # os pixels descomprimidos sem adicionar nova camada lossy.
            img.save(output_path)

        elapsed = time.time() - start_time
        restored_size = os.path.getsize(output_path)

        return {
            'input_file': input_path,
            'output_file': output_path,
            'original_format': header.get('original_format', 'UNKNOWN'),
            'lossless': False,
            'width': width,
            'height': height,
            'total_pixels': width * height,
            'megapixels': round(width * height / 1_000_000, 3),
            'has_alpha': has_alpha,
            'pp_size': pp_file_size,
            'restored_size': restored_size,
            'quality': quality,
            'psnr': None,
            'psnr_str': 'N/A (arquivo original necessario)',
            'integrity_verified': None,
            'time_seconds': round(elapsed, 3),
            'pixels_per_second': int(width * height / elapsed) if elapsed > 0 else 0,
        }


# ==============================================================
# Compressao universal (qualquer tipo de arquivo)
# ==============================================================

def _is_image_path(path: str) -> bool:
    """Detecta se um arquivo e imagem pela extensao."""
    ext = os.path.splitext(path)[1].lower()
    image_exts = {
        '.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif', '.webp',
        '.ico', '.tga', '.ppm', '.pgm', '.pbm', '.pnm', '.jp2', '.jpx',
        '.j2k', '.j2c', '.pcx', '.psd', '.dds', '.xbm', '.xpm', '.dib',
        '.sgi', '.apng', '.jfif',
    }
    return ext in image_exts


def compress_file(input_path: str, output_path: str = None) -> dict:
    """
    Comprime QUALQUER arquivo para o formato .PP usando compressao universal.
    Sempre lossless (sem perdas). Inspirado no 7-Zip e WinRAR.

    Pipeline:
      1. Le bytes brutos do arquivo
      2. Testa LZMA (7-Zip), BZ2 (bzip2), DEFLATE (zlib), BWT+MTF, Delta+LZMA
      3. Escolhe a estrategia com melhor compressao
      4. Empacota no container .PP com verificacao SHA-256

    Args:
        input_path:  Caminho do arquivo de entrada (qualquer formato)
        output_path: Caminho do arquivo .PP (auto-detectado se None)

    Returns:
        Dicionario com estatisticas completas da compressao
    """
    from pied_piper.compressors.pipeline import compress_universal

    start_time = time.time()

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Arquivo nao encontrado: {input_path}")

    if output_path is None:
        base = os.path.splitext(input_path)[0]
        output_path = base + PP_EXTENSION

    original_size = os.path.getsize(input_path)
    filename = os.path.basename(input_path)
    original_ext = os.path.splitext(input_path)[1]

    with open(input_path, 'rb') as f:
        raw_data = f.read()

    # Comprime usando pipeline universal
    compressed_payload, comp_stats = compress_universal(raw_data)

    # Monta header JSON
    header = {
        'version': PP_VERSION,
        'codec': 4,
        'universal': True,
        'lossless': True,
        'filename': filename,
        'original_ext': original_ext,
        'original_size': original_size,
        'strategy': comp_stats['strategy_name'],
        'hash': comp_stats['hash'],
    }

    header_json = json.dumps(header, separators=(',', ':')).encode('utf-8')

    with open(output_path, 'wb') as f:
        f.write(PP_MAGIC)
        f.write(struct.pack('<H', PP_VERSION))
        f.write(struct.pack('<I', len(header_json)))
        f.write(header_json)
        f.write(struct.pack('<I', len(compressed_payload)))
        f.write(compressed_payload)

    elapsed = time.time() - start_time
    output_size = os.path.getsize(output_path)

    ratio = original_size / output_size if output_size > 0 else 0
    reduction = (1 - output_size / original_size) * 100 if original_size > 0 else 0

    return {
        'input_file': input_path,
        'output_file': output_path,
        'filename': filename,
        'original_ext': original_ext,
        'original_size': original_size,
        'compressed_size': output_size,
        'payload_size': comp_stats['compressed_size'],
        'compression_ratio': round(ratio, 2),
        'reduction_percent': round(reduction, 2),
        'strategy': comp_stats['strategy_name'],
        'all_results': comp_stats.get('all_results', {}),
        'hash': comp_stats['hash'],
        'lossless': True,
        'universal': True,
        'time_seconds': round(elapsed, 3),
        'bytes_per_second': int(original_size / elapsed) if elapsed > 0 else 0,
    }


def decompress_file(input_path: str, output_path: str = None) -> dict:
    """
    Descomprime um arquivo .PP universal de volta ao formato original.

    Args:
        input_path:  Caminho do arquivo .PP
        output_path: Caminho de saida (auto-detectado se None)

    Returns:
        Dicionario com estatisticas da descompressao
    """
    from pied_piper.compressors.pipeline import decompress_universal

    start_time = time.time()

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Arquivo nao encontrado: {input_path}")

    with open(input_path, 'rb') as f:
        magic = f.read(4)
        if magic != PP_MAGIC:
            raise ValueError(f"Arquivo invalido: nao e um arquivo .PP")
        version = struct.unpack('<H', f.read(2))[0]
        header_size = struct.unpack('<I', f.read(4))[0]
        header = json.loads(f.read(header_size).decode('utf-8'))
        data_size = struct.unpack('<I', f.read(4))[0]
        raw_payload = f.read(data_size)

    if not header.get('universal', False):
        raise ValueError("Este arquivo .PP nao e universal. Use decompress().")

    filename = header.get('filename', 'output')
    original_ext = header.get('original_ext', '')

    if output_path is None:
        base = os.path.splitext(input_path)[0]
        output_path = base + '_restored' + original_ext

    # Descomprime usando pipeline universal
    original_data, dec_stats = decompress_universal(raw_payload)

    with open(output_path, 'wb') as f:
        f.write(original_data)

    elapsed = time.time() - start_time
    pp_size = os.path.getsize(input_path)
    restored_size = os.path.getsize(output_path)

    return {
        'input_file': input_path,
        'output_file': output_path,
        'filename': filename,
        'original_ext': original_ext,
        'original_size': header.get('original_size', 0),
        'pp_size': pp_size,
        'restored_size': restored_size,
        'strategy': dec_stats['strategy_name'],
        'integrity_verified': dec_stats['integrity_verified'],
        'hash': dec_stats['hash'],
        'lossless': True,
        'universal': True,
        'time_seconds': round(elapsed, 3),
        'bytes_per_second': int(restored_size / elapsed) if elapsed > 0 else 0,
    }


def is_universal(input_path: str) -> bool:
    """Retorna True se o arquivo .PP e formato universal (nao-imagem)."""
    if not os.path.exists(input_path):
        return False
    try:
        with open(input_path, 'rb') as f:
            magic = f.read(4)
            if magic != PP_MAGIC:
                return False
            f.read(2)  # version
            header_size = struct.unpack('<I', f.read(4))[0]
            header = json.loads(f.read(header_size).decode('utf-8'))
        return header.get('universal', False)
    except Exception:
        return False


def smart_compress(input_path: str, output_path: str = None,
                   quality: int = 75, lossless: bool = False) -> dict:
    """
    Comprime qualquer arquivo de forma inteligente:
    - Se for imagem: usa pipeline de imagem (lossy ou lossless)
    - Se nao for imagem: usa pipeline universal (sempre lossless)

    Esta funcao substitui compress() como ponto de entrada principal.
    """
    if os.path.isdir(input_path):
        return compress_folder(input_path, output_path,
                               quality=quality, lossless=lossless)

    # Tenta como imagem primeiro
    if _is_image_path(input_path):
        try:
            img = Image.open(input_path)
            img.verify()
            return compress(input_path, output_path, quality, lossless)
        except Exception:
            pass  # Nao e imagem valida, usa universal

    # Qualquer outro arquivo: compressao universal
    return compress_file(input_path, output_path)


def smart_decompress(input_path: str, output_path: str = None) -> dict:
    """
    Descomprime qualquer arquivo .PP de forma inteligente:
    - Se for bundle: usa decompress_bundle()
    - Se for universal: usa decompress_file()
    - Se for imagem: usa decompress()
    """
    if is_bundle(input_path):
        return decompress_bundle(input_path, output_path)
    if is_universal(input_path):
        return decompress_file(input_path, output_path)
    return decompress(input_path, output_path)


# ==============================================================
# Info - le header sem descomprimir
# ==============================================================

def info(input_path: str) -> dict:
    """Retorna informacoes de um arquivo .PP sem descomprimir."""
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Arquivo nao encontrado: {input_path}")

    with open(input_path, 'rb') as f:
        magic = f.read(4)
        if magic != PP_MAGIC:
            raise ValueError(f"Nao e um arquivo .PP valido")
        version = struct.unpack('<H', f.read(2))[0]
        header_size = struct.unpack('<I', f.read(4))[0]
        header_json = f.read(header_size)
        header = json.loads(header_json.decode('utf-8'))
        data_size = struct.unpack('<I', f.read(4))[0]

    file_size = os.path.getsize(input_path)

    # Arquivo universal (nao-imagem)
    if header.get('universal', False):
        return {
            'file': input_path,
            'file_size': file_size,
            'version': version,
            'header_size': header_size,
            'data_size': data_size,
            'universal': True,
            'filename': header.get('filename', 'N/A'),
            'original_ext': header.get('original_ext', 'N/A'),
            'original_size': header.get('original_size', 0),
            'strategy': header.get('strategy', 'N/A'),
            'lossless': True,
            'hash': header.get('hash', 'N/A'),
        }

    return {
        'file': input_path,
        'file_size': file_size,
        'version': version,
        'header_size': header_size,
        'data_size': data_size,
        'width': header.get('width', 0),
        'height': header.get('height', 0),
        'quality': header.get('quality', 0),
        'has_alpha': header.get('has_alpha', False),
        'lossless': header.get('lossless', False),
        'original_format': header.get('original_format', 'N/A'),
        'original_mode': header.get('original_mode', 'N/A'),
        'total_pixels': header.get('width', 0) * header.get('height', 0),
    }


def engine_info() -> dict:
    """Retorna informacoes sobre o motor de compressao."""
    lib = _load_engine()
    return {
        'engine': 'C (libmiddleout) + Python (universal)',
        'c_engine_available': lib is not None,
        'library_path': _find_engine_library() or 'nao encontrada',
        'languages': 'C (motor) + Python (codec/universal) + Shell (launcher) + NASM Assembly (DCT)',
        'format_version': PP_VERSION,
        'lossless_available': True,
        'universal_available': True,
        'algorithms': [
            'LZMA (7-Zip)', 'BZ2 (bzip2)', 'DEFLATE (zlib)',
            'BWT+MTF (Burrows-Wheeler)', 'Delta+LZMA',
            'DCT+Quantizacao (imagens lossy)',
            'RCT+DPCM (imagens lossless)',
        ],
    }


# ==============================================================
# Extensoes de imagem suportadas (para varredura de pastas)
# ==============================================================

_IMAGE_EXTS = frozenset({
    '.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif', '.webp',
    '.ico', '.tga', '.ppm', '.pgm', '.pbm', '.pnm', '.jp2', '.jpx',
    '.j2k', '.j2c', '.pcx', '.psd', '.dds',
})


def _is_image_file(path: str) -> bool:
    """Retorna True se a extensao do arquivo e de imagem suportada."""
    return os.path.splitext(path)[1].lower() in _IMAGE_EXTS


# ==============================================================
# Compressao de pastas (bundle .PP)
# ==============================================================

def compress_folder(folder_path: str, output_path: str = None,
                    quality: int = 75, lossless: bool = True) -> dict:
    """
    Comprime TODOS os arquivos de uma pasta em um unico arquivo .PP bundle.

    Imagens sao comprimidas com o pipeline de imagem (lossy ou lossless).
    Demais arquivos sao comprimidos com o pipeline universal (sempre lossless).

    Args:
        folder_path:  Caminho da pasta com arquivos
        output_path:  Caminho do bundle .PP (auto-detectado se None)
        quality:      Qualidade 1-100 (so usado em modo lossy para imagens)
        lossless:     True = sem perdas (padrao); False = lossy (so imagens)

    Returns:
        Dicionario com estatisticas do bundle
    """
    import tempfile

    if not os.path.isdir(folder_path):
        raise ValueError(f"Nao e uma pasta: {folder_path}")

    folder_abs  = os.path.abspath(folder_path)
    folder_name = os.path.basename(folder_abs)

    if output_path is None:
        parent      = os.path.dirname(folder_abs)
        output_path = os.path.join(parent, folder_name + PP_EXTENSION)

    start_time = time.time()

    # Varre TODOS os arquivos (top-level, ordenado)
    all_entries   = sorted(os.listdir(folder_abs))
    image_files   = []
    other_files   = []
    skipped_files = []

    for fname in all_entries:
        fpath = os.path.join(folder_abs, fname)
        if not os.path.isfile(fpath):
            continue
        if _is_image_file(fpath):
            try:
                _test = Image.open(fpath)
                _test.verify()
                image_files.append(fname)
            except Exception:
                other_files.append(fname)
        else:
            other_files.append(fname)

    all_files = image_files + other_files
    if not all_files:
        raise ValueError(f"Nenhum arquivo encontrado em: {folder_path}")

    file_entries        = []
    all_pp_payloads     = []
    current_offset      = 0
    total_original_size = 0

    for fname in all_files:
        fpath = os.path.join(folder_abs, fname)

        # Comprime para arquivo .PP temporario
        with tempfile.NamedTemporaryFile(suffix='.PP', delete=False) as _tmp:
            tmp_path = _tmp.name
        try:
            if fname in image_files:
                stats = compress(fpath, tmp_path, quality=quality, lossless=lossless)
            else:
                stats = compress_file(fpath, tmp_path)
            with open(tmp_path, 'rb') as _f:
                pp_bytes = _f.read()
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

        entry = {
            'name':             fname,
            'offset':           current_offset,
            'size':             len(pp_bytes),
            'original_size':    stats['original_size'],
            'compressed_size':  stats['compressed_size'],
        }
        if stats.get('universal'):
            entry['universal'] = True
            entry['format'] = stats.get('original_ext', '')
        else:
            entry['width'] = stats.get('width', 0)
            entry['height'] = stats.get('height', 0)
            entry['format'] = stats.get('original_format', '')
        file_entries.append(entry)
        all_pp_payloads.append(pp_bytes)
        current_offset      += len(pp_bytes)
        total_original_size += stats['original_size']

    # Monta o bundle
    bundle_header = {
        'version':       PP_VERSION,
        'codec':         4,
        'bundle':        True,
        'source_folder': folder_name,
        'file_count':    len(file_entries),
        'lossless':      lossless,
        'quality':       100 if lossless else quality,
        'files':         file_entries,
    }
    bundle_header_json = json.dumps(bundle_header, separators=(',', ':')).encode('utf-8')
    bundle_data        = b''.join(all_pp_payloads)

    with open(output_path, 'wb') as _f:
        _f.write(PP_MAGIC)
        _f.write(struct.pack('<H', PP_VERSION))
        _f.write(struct.pack('<I', len(bundle_header_json)))
        _f.write(bundle_header_json)
        _f.write(struct.pack('<I', len(bundle_data)))
        _f.write(bundle_data)

    elapsed              = time.time() - start_time
    total_compressed     = os.path.getsize(output_path)
    ratio                = (total_original_size / total_compressed
                            if total_compressed > 0 else 0)
    reduction            = ((1 - total_compressed / total_original_size) * 100
                            if total_original_size > 0 else 0)

    return {
        'input_folder':          folder_path,
        'output_file':           output_path,
        'total_images':          len(image_files),
        'total_other_files':     len(other_files),
        'total_files':           len(all_files),
        'skipped_files':         skipped_files,
        'total_original_size':   total_original_size,
        'total_compressed_size': total_compressed,
        'compression_ratio':     round(ratio, 2),
        'reduction_percent':     round(reduction, 2),
        'lossless':              lossless,
        'quality':               100 if lossless else quality,
        'time_seconds':          round(elapsed, 3),
        'file_entries':          file_entries,
    }


# ==============================================================
# Descompressao de bundles (pastas)
# ==============================================================

def decompress_bundle(input_path: str, output_dir: str = None) -> dict:
    """
    Descomprime um bundle .PP (pasta comprimida) para um diretorio.

    Args:
        input_path: Caminho do arquivo .PP bundle
        output_dir: Diretorio de saida (auto-detectado se None)

    Returns:
        Dicionario com estatisticas da extracao
    """
    import tempfile

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Arquivo nao encontrado: {input_path}")

    start_time = time.time()

    with open(input_path, 'rb') as _f:
        magic = _f.read(4)
        if magic != PP_MAGIC:
            raise ValueError(f"Arquivo invalido: nao e um .PP bundle")
        _version     = struct.unpack('<H', _f.read(2))[0]
        header_size  = struct.unpack('<I', _f.read(4))[0]
        header       = json.loads(_f.read(header_size).decode('utf-8'))
        data_size    = struct.unpack('<I', _f.read(4))[0]
        bundle_data  = _f.read(data_size)

    if not header.get('bundle', False):
        raise ValueError(
            "Este arquivo nao e um bundle. Use decompress() para imagens individuais."
        )

    source_folder = header.get('source_folder', 'extracted')
    if output_dir is None:
        base       = os.path.splitext(input_path)[0]
        output_dir = base + '_extracted'

    os.makedirs(output_dir, exist_ok=True)

    file_entries = header.get('files', [])
    results      = []

    for entry in file_entries:
        offset   = entry['offset']
        size     = entry['size']
        fname    = entry['name']
        pp_bytes = bundle_data[offset:offset + size]

        # Escreve PP individual em arquivo temporario e descomprime
        with tempfile.NamedTemporaryFile(suffix='.PP', delete=False) as _tmp:
            _tmp.write(pp_bytes)
            tmp_path = _tmp.name

        try:
            # Detecta tipo e descomprime adequadamente
            if is_universal(tmp_path):
                stats   = decompress_file(tmp_path, output_path=None)
            else:
                stats   = decompress(tmp_path, output_path=None)
            tmp_out    = stats['output_file']

            # Renomeia para o nome original (sem sufixo _restored)
            base_name  = os.path.splitext(fname)[0]
            out_ext    = os.path.splitext(tmp_out)[1]
            final_name = base_name + out_ext
            final_path = os.path.join(output_dir, final_name)

            # Evita colisoes de nome
            if os.path.exists(final_path):
                final_name = base_name + '_restored' + out_ext
                final_path = os.path.join(output_dir, final_name)

            os.rename(tmp_out, final_path)

            results.append({
                'name':          final_name,
                'original_name': fname,
                'size':          os.path.getsize(final_path),
                'ok':            True,
            })
        except Exception as _e:
            results.append({'name': fname, 'ok': False, 'error': str(_e)})
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    elapsed = time.time() - start_time

    return {
        'input_file':      input_path,
        'output_dir':      output_dir,
        'source_folder':   source_folder,
        'files_extracted': len([r for r in results if r['ok']]),
        'files_failed':    len([r for r in results if not r['ok']]),
        'results':         results,
        'lossless':        header.get('lossless', False),
        'time_seconds':    round(elapsed, 3),
    }


# ==============================================================
# Avaliacao de qualidade: compara original vs restaurada
# ==============================================================

def _compute_ssim(img1: np.ndarray, img2: np.ndarray) -> float:
    """
    Calcula SSIM (Structural Similarity Index) entre dois arrays RGB float64.
    Usa scipy.ndimage se disponivel, caso contrario usa janelas 8x8.
    """
    C1 = (0.01 * 255) ** 2
    C2 = (0.03 * 255) ** 2

    # Converte para escala de cinza
    g1 = 0.299 * img1[..., 0] + 0.587 * img1[..., 1] + 0.114 * img1[..., 2]
    g2 = 0.299 * img2[..., 0] + 0.587 * img2[..., 1] + 0.114 * img2[..., 2]

    try:
        from scipy.ndimage import uniform_filter
        w = 11
        mu1 = uniform_filter(g1, w)
        mu2 = uniform_filter(g2, w)
        mu1_sq  = mu1 ** 2
        mu2_sq  = mu2 ** 2
        mu1_mu2 = mu1 * mu2
        s1  = uniform_filter(g1 * g1, w) - mu1_sq
        s2  = uniform_filter(g2 * g2, w) - mu2_sq
        s12 = uniform_filter(g1 * g2, w) - mu1_mu2
        ssim_map = ((2 * mu1_mu2 + C1) * (2 * s12 + C2)) / (
            (mu1_sq + mu2_sq + C1) * (s1 + s2 + C2)
        )
        return float(np.mean(ssim_map))
    except ImportError:
        pass

    # Fallback: janelas 8x8
    h, w = g1.shape
    step = 8
    ssim_vals = []
    for i in range(0, h - step + 1, step):
        for j in range(0, w - step + 1, step):
            p1 = g1[i:i + step, j:j + step].flatten().astype(np.float64)
            p2 = g2[i:i + step, j:j + step].flatten().astype(np.float64)
            mu1_p = p1.mean()
            mu2_p = p2.mean()
            s1_p  = float(np.mean((p1 - mu1_p) ** 2))
            s2_p  = float(np.mean((p2 - mu2_p) ** 2))
            s12_p = float(np.mean((p1 - mu1_p) * (p2 - mu2_p)))
            num   = (2 * mu1_p * mu2_p + C1) * (2 * s12_p + C2)
            den   = (mu1_p ** 2 + mu2_p ** 2 + C1) * (s1_p + s2_p + C2)
            ssim_vals.append(num / den if den != 0 else 1.0)
    return float(np.mean(ssim_vals)) if ssim_vals else 1.0


def quality_check(original_path: str, restored_path: str) -> dict:
    """
    Avalia a qualidade de uma imagem restaurada comparando com o original.

    Calcula:
      - PSNR (Peak Signal-to-Noise Ratio) geral e por canal RGB
      - SSIM (Structural Similarity Index)
      - MSE (Mean Squared Error), MAE (Mean Absolute Error)
      - Diferenca maxima de pixels
      - Comparacao de tamanho de arquivo

    Args:
        original_path:  Caminho da imagem original
        restored_path:  Caminho da imagem restaurada / descomprimida

    Returns:
        Dicionario com todas as metricas de qualidade
    """
    start = time.time()

    if not os.path.exists(original_path):
        raise FileNotFoundError(f"Original nao encontrado: {original_path}")
    if not os.path.exists(restored_path):
        raise FileNotFoundError(f"Imagem restaurada nao encontrada: {restored_path}")

    orig_arr, orig_meta = _load_any_image(original_path)
    rest_arr, rest_meta = _load_any_image(restored_path)

    orig_size = os.path.getsize(original_path)
    rest_size = os.path.getsize(restored_path)

    if orig_arr.shape[:2] != rest_arr.shape[:2]:
        raise ValueError(
            f"Dimensoes incompativeis: original {orig_arr.shape[:2]} "
            f"vs restaurada {rest_arr.shape[:2]}"
        )

    # Garante 3 canais RGB
    def to_rgb3(arr):
        if arr.ndim == 2:
            return np.stack([arr] * 3, axis=-1).astype(np.float64)
        return arr[..., :3].astype(np.float64)

    orig_rgb = to_rgb3(orig_arr)
    rest_rgb = to_rgb3(rest_arr)

    height, width = orig_rgb.shape[:2]
    total_pixels  = height * width

    # PSNR por canal R, G, B
    ch_names = ['R', 'G', 'B']
    ch_psnr  = {}
    ch_mse   = {}
    for idx, name in enumerate(ch_names):
        mse = float(np.mean((orig_rgb[..., idx] - rest_rgb[..., idx]) ** 2))
        ch_mse[name]  = mse
        ch_psnr[name] = (10.0 * np.log10(255.0 ** 2 / mse)
                         if mse > 0 else float('inf'))

    # PSNR geral (todos os canais)
    overall_mse  = float(np.mean((orig_rgb - rest_rgb) ** 2))
    overall_psnr = (10.0 * np.log10(255.0 ** 2 / overall_mse)
                    if overall_mse > 0 else float('inf'))

    # MAE e diferenca maxima
    diff = np.abs(orig_rgb - rest_rgb)
    mae      = float(np.mean(diff))
    max_diff = float(np.max(diff))

    # SSIM
    ssim_val = _compute_ssim(orig_rgb, rest_rgb)

    # Percentual de pixels alterados (diferenca > 1 nivel)
    changed_pixels = int(np.sum(np.max(diff, axis=-1) > 1.0))
    changed_pct    = round(changed_pixels / total_pixels * 100, 3)

    # Avaliacao de qualidade por PSNR
    if overall_psnr == float('inf'):
        quality_label = 'IDENTICA (pixel-perfeito)'
        quality_level = 'perfect'
    elif overall_psnr >= 40:
        quality_label = 'EXCELENTE'
        quality_level = 'excellent'
    elif overall_psnr >= 35:
        quality_label = 'MUITO BOA'
        quality_level = 'very_good'
    elif overall_psnr >= 30:
        quality_label = 'BOA'
        quality_level = 'good'
    elif overall_psnr >= 25:
        quality_label = 'REGULAR'
        quality_level = 'fair'
    else:
        quality_label = 'RUIM (perda significativa)'
        quality_level = 'poor'

    elapsed = time.time() - start

    return {
        'original_path':   original_path,
        'restored_path':   restored_path,
        'original_format': orig_meta['original_format'],
        'restored_format': rest_meta['original_format'],
        'width':           width,
        'height':          height,
        'total_pixels':    total_pixels,
        'megapixels':      round(total_pixels / 1_000_000, 3),
        'original_size':   orig_size,
        'restored_size':   rest_size,
        'size_ratio':      round(rest_size / orig_size, 4) if orig_size > 0 else 0,
        'size_diff_pct':   round((rest_size - orig_size) / orig_size * 100, 2)
                           if orig_size > 0 else 0,
        'psnr':            overall_psnr,
        'psnr_str':        ('inf (identico)' if overall_psnr == float('inf')
                            else f'{overall_psnr:.2f} dB'),
        'ssim':            ssim_val,
        'ssim_str':        f'{ssim_val:.6f}',
        'mse':             overall_mse,
        'mae':             mae,
        'max_diff':        max_diff,
        'channel_psnr':    ch_psnr,
        'channel_mse':     ch_mse,
        'changed_pixels':  changed_pixels,
        'changed_pct':     changed_pct,
        'quality_label':   quality_label,
        'quality_level':   quality_level,
        'time_seconds':    round(elapsed, 3),
    }


def is_bundle(input_path: str) -> bool:
    """Retorna True se o arquivo .PP e um bundle de pasta."""
    if not os.path.exists(input_path):
        return False
    try:
        with open(input_path, 'rb') as _f:
            magic = _f.read(4)
            if magic != PP_MAGIC:
                return False
            _f.read(2)  # version
            header_size = struct.unpack('<I', _f.read(4))[0]
            header      = json.loads(_f.read(header_size).decode('utf-8'))
        return header.get('bundle', False)
    except Exception:
        return False
