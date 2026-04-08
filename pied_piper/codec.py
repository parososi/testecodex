"""
Pied Piper Codec - Wrapper Python do motor C Middle-Out.

Este modulo faz a ponte entre Python e o motor C de alta performance,
e gerencia todo o pipeline de compressao/descompressao de imagens .PP

Modos suportados:
  - Lossy  (padrao): DCT + quantizacao adaptativa + espiral Middle-Out
  - Lossless (-l):   DPCM entre blocos na espiral Middle-Out, sem perdas
                     Transformada de cor reversivel (RCT) preserva pixels exatos
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
PP_VERSION = 3              # v3: adiciona modo lossless + RCT
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
        os.path.join(here, 'libmiddleout.so'),
        os.path.join(here, 'libmiddleout.dylib'),
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

        # libc para free() — tipo explicito por seguranca cross-platform
        libc_name = None
        try:
            libc = ctypes.CDLL(None)
        except OSError:
            libc = ctypes.CDLL("libc.so.6")
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
# Pipeline Middle-Out Lossless (C engine)
# ==============================================================

def _compress_lossless_channel_c(channel: np.ndarray) -> tuple:
    """
    Comprime canal int16 usando Middle-Out DPCM lossless.
    Retorna (bytes_comprimidos, MOStats).
    """
    lib = _load_engine()
    if not lib:
        raise RuntimeError("Motor C nao disponivel")

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
        raise RuntimeError("Falha na compressao lossless do canal")

    data = bytes(ctypes.string_at(ptr, size_out.value))
    _LIBC.free(ptr)
    return data, stats


def _decompress_lossless_channel_c(data: bytes, width: int,
                                    height: int) -> np.ndarray:
    """
    Descomprime canal lossless produzido por _compress_lossless_channel_c.
    Retorna array int16 shape (height, width).
    """
    lib = _load_engine()
    if not lib:
        raise RuntimeError("Motor C nao disponivel")

    buf = (c_uint8 * len(data)).from_buffer_copy(data)

    ptr = lib.mo_decompress_lossless_ch(
        buf, c_int(len(data)),
        c_int(width), c_int(height),
    )

    if not ptr:
        raise RuntimeError("Falha na descompressao lossless do canal")

    int16_ptr = ctypes.cast(ptr, POINTER(c_int16))
    arr = np.ctypeslib.as_array(int16_ptr, shape=(height, width)).copy()
    _LIBC.free(ptr)
    return arr


# ==============================================================
# Pipeline Middle-Out (C engine) - LOSSY
# ==============================================================

def _compress_channel_c(channel: np.ndarray, quant_table: np.ndarray,
                        quality: int) -> bytes:
    """Comprime canal usando motor C."""
    lib = _load_engine()
    if not lib:
        raise RuntimeError("Motor C nao disponivel. Execute 'make' em engine/")

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
        raise RuntimeError("Falha na compressao do canal")

    # Copia dados do ponteiro C para bytes Python
    data = bytes(ctypes.string_at(ptr, size_out.value))
    # Libera memoria alocada pelo C
    _LIBC.free(ptr)
    return data, stats


def _decompress_channel_c(data: bytes, width: int, height: int,
                          quant_table: np.ndarray, quality: int) -> np.ndarray:
    """Descomprime canal usando motor C."""
    lib = _load_engine()
    if not lib:
        raise RuntimeError("Motor C nao disponivel")

    qflat = np.ascontiguousarray(quant_table.flatten(), dtype=np.float64)
    buf = (c_uint8 * len(data)).from_buffer_copy(data)

    ptr = lib.mo_decompress_channel(
        buf, c_int(len(data)),
        c_int(width), c_int(height),
        qflat.ctypes.data_as(POINTER(c_double)),
        c_int(quality),
    )

    if not ptr:
        raise RuntimeError("Falha na descompressao do canal")

    # Cast void* para double* para ler como array
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

    if not _load_engine():
        raise RuntimeError(
            "Motor C nao encontrado. Compile com: cd engine && make"
        )

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
        # Pipeline Lossless: RCT + Middle-Out DPCM por canal
        # ============================================================
        y_ch, cb_ch, cr_ch = _rct_forward(rgb)   # RCT: Y, Cb, Cr (int16)

        y_data,  y_stats  = _compress_lossless_channel_c(y_ch)
        cb_data, cb_stats = _compress_lossless_channel_c(cb_ch)
        cr_data, cr_stats = _compress_lossless_channel_c(cr_ch)

        alpha_data = None
        alpha_stats = None
        if has_alpha:
            alpha_ch = alpha_u8.astype(np.int16)
            alpha_data, alpha_stats = _compress_lossless_channel_c(alpha_ch)

        header = {
            'version': PP_VERSION,
            'lossless': True,
            'width': int(width),
            'height': int(height),
            'quality': 100,
            'has_alpha': bool(has_alpha),
            'original_format': metadata['original_format'],
            'original_mode': metadata['original_mode'],
            'original_hash': original_hash,
            'y_size':    len(y_data),
            'cb_size':   len(cb_data),
            'cr_size':   len(cr_data),
            'alpha_size': len(alpha_data) if alpha_data else 0,
        }

        all_data = y_data + cb_data + cr_data
        if alpha_data:
            all_data += alpha_data

        total_blocks = (y_stats.total_blocks + cb_stats.total_blocks +
                        cr_stats.total_blocks)
        predicted = (y_stats.predicted_blocks + cb_stats.predicted_blocks +
                     cr_stats.predicted_blocks)
        avg_sparsity = (y_stats.sparsity + cb_stats.sparsity +
                        cr_stats.sparsity) / 3

    else:
        # ============================================================
        # Pipeline Lossy: DCT + Quantizacao Adaptativa Middle-Out
        # ============================================================
        ycbcr = _rgb_to_ycbcr(rgb)
        y_channel  = ycbcr[..., 0]
        cb_channel = ycbcr[..., 1]
        cr_channel = ycbcr[..., 2]

        cb_sub = _subsample_420(cb_channel)
        cr_sub = _subsample_420(cr_channel)

        quant_y = _get_quant_table(QUANT_LUMINANCE,   quality)
        quant_c = _get_quant_table(QUANT_CHROMINANCE,  quality)

        y_data,  y_stats  = _compress_channel_c(y_channel, quant_y, quality)
        cb_data, cb_stats = _compress_channel_c(cb_sub,    quant_c, quality)
        cr_data, cr_stats = _compress_channel_c(cr_sub,    quant_c, quality)

        alpha_data = None
        alpha_stats = None
        if has_alpha:
            quant_a = _get_quant_table(QUANT_LUMINANCE, max(quality, 90))
            alpha_data, alpha_stats = _compress_channel_c(
                alpha_u8.astype(np.float64), quant_a, quality)

        header = {
            'version': PP_VERSION,
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

        total_blocks = (y_stats.total_blocks + cb_stats.total_blocks +
                        cr_stats.total_blocks)
        predicted = (y_stats.predicted_blocks + cb_stats.predicted_blocks +
                     cr_stats.predicted_blocks)
        avg_sparsity = (y_stats.sparsity + cb_stats.sparsity +
                        cr_stats.sparsity) / 3

        zero_blocks = (y_stats.zero_blocks + cb_stats.zero_blocks +
                       cr_stats.zero_blocks)

    header_json = json.dumps(header, separators=(',', ':')).encode('utf-8')
    final_compressed = zlib.compress(all_data, level=9)

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
        zero_blocks_val = (y_stats.zero_blocks + cb_stats.zero_blocks +
                           cr_stats.zero_blocks)
        result['zero_blocks'] = int(zero_blocks_val)
        result['zero_blocks_percent'] = round(
            (zero_blocks_val / total_blocks * 100) if total_blocks > 0 else 0, 2)
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
    start_time = time.time()

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Arquivo nao encontrado: {input_path}")

    if output_path is None:
        base = os.path.splitext(input_path)[0]
        output_path = base + '_restored.png'

    if not _load_engine():
        raise RuntimeError("Motor C nao encontrado")

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
        final_compressed = f.read(data_size)

    pp_file_size = os.path.getsize(input_path)
    all_data = zlib.decompress(final_compressed)

    width     = header['width']
    height    = header['height']
    quality   = header['quality']
    has_alpha = header['has_alpha']
    is_lossless = header.get('lossless', False)

    if is_lossless:
        # ============================================================
        # Descompressao Lossless: Middle-Out DPCM -> RCT inversa
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

        y_ch  = _decompress_lossless_channel_c(y_data,  width, height)
        cb_ch = _decompress_lossless_channel_c(cb_data, width, height)
        cr_ch = _decompress_lossless_channel_c(cr_data, width, height)

        rgb = _rct_inverse(y_ch, cb_ch, cr_ch)

        if has_alpha and alpha_data:
            alpha_ch = _decompress_lossless_channel_c(alpha_data, width, height)
            alpha = np.clip(alpha_ch, 0, 255).astype(np.uint8)
            img = Image.fromarray(np.dstack([rgb, alpha]), 'RGBA')
            restored_array = np.dstack([rgb, alpha])
        else:
            img = Image.fromarray(rgb, 'RGB')
            restored_array = rgb

        img.save(output_path)

        # Verificacao de integridade lossless
        restored_hash = _sha256_array(restored_array)
        original_hash = header.get('original_hash', '')
        verified = (original_hash == restored_hash) if original_hash else None

        elapsed = time.time() - start_time
        restored_size = os.path.getsize(output_path)

        return {
            'input_file': input_path,
            'output_file': output_path,
            'original_format': header.get('original_format', 'UNKNOWN'),
            'lossless': True,
            'width': width,
            'height': height,
            'total_pixels': width * height,
            'megapixels': round(width * height / 1_000_000, 3),
            'has_alpha': has_alpha,
            'pp_size': pp_file_size,
            'restored_size': restored_size,
            'quality': 100,
            'psnr': float('inf'),
            'psnr_str': 'LOSSLESS (perfeito)',
            'integrity_verified': verified,
            'original_hash': original_hash,
            'restored_hash': restored_hash,
            'time_seconds': round(elapsed, 3),
            'pixels_per_second': int(width * height / elapsed) if elapsed > 0 else 0,
        }

    else:
        # ============================================================
        # Descompressao Lossy: IDCT + Dequantizacao
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

        y_channel = _decompress_channel_c(y_data, width, height, quant_y, quality)

        cb_h, cb_w = header['cb_shape']
        cr_h, cr_w = header['cr_shape']
        cb_sub = _decompress_channel_c(cb_data, cb_w, cb_h, quant_c, quality)
        cr_sub = _decompress_channel_c(cr_data, cr_w, cr_h, quant_c, quality)

        cb_full = _upsample_420(cb_sub, height, width)
        cr_full = _upsample_420(cr_sub, height, width)

        ycbcr = np.stack([y_channel, cb_full, cr_full], axis=-1)
        rgb   = _ycbcr_to_rgb(ycbcr)

        if has_alpha and alpha_data:
            quant_a = _get_quant_table(QUANT_LUMINANCE, max(quality, 90))
            alpha = _decompress_channel_c(alpha_data, width, height, quant_a, quality)
            alpha = np.clip(alpha, 0, 255).astype(np.uint8)
            img = Image.fromarray(np.dstack([rgb, alpha]), 'RGBA')
        else:
            img = Image.fromarray(rgb, 'RGB')

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
    return {
        'file': input_path,
        'file_size': file_size,
        'version': version,
        'header_size': header_size,
        'data_size': data_size,
        'width': header['width'],
        'height': header['height'],
        'quality': header['quality'],
        'has_alpha': header['has_alpha'],
        'lossless': header.get('lossless', False),
        'original_format': header.get('original_format', 'N/A'),
        'original_mode': header.get('original_mode', 'N/A'),
        'total_pixels': header['width'] * header['height'],
    }


def engine_info() -> dict:
    """Retorna informacoes sobre o motor de compressao."""
    lib = _load_engine()
    return {
        'engine': 'C (libmiddleout)' if lib else 'Nao disponivel',
        'c_engine_available': lib is not None,
        'library_path': _find_engine_library() or 'nao encontrada',
        'languages': 'C (motor) + Python (codec) + Shell (launcher) + NASM Assembly (DCT)',
        'format_version': PP_VERSION,
        'lossless_available': lib is not None,
    }
