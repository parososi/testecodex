"""
Pied Piper Codec - Algoritmo de compressao de imagens .PP

O formato .PP utiliza uma combinacao de tecnicas:
1. Conversao para espaco de cores YCbCr (separacao luminancia/crominancia)
2. Subamostragem de crominancia 4:2:0 (o olho humano e menos sensivel a cor)
3. Transformada DCT (Discrete Cosine Transform) em blocos 8x8
4. Quantizacao adaptativa baseada em qualidade
5. Codificacao Run-Length (RLE) para zeros apos quantizacao
6. Compressao zlib final

Estrutura do arquivo .PP:
  [MAGIC 4B] [VERSION 2B] [HEADER_SIZE 4B] [HEADER JSON] [DATA comprimido]
"""

import struct
import json
import zlib
import time
import math
from typing import Tuple, Dict, Any

import numpy as np
from PIL import Image

# Magic number: "PP" em bytes
PP_MAGIC = b'\x50\x50\x43\x4D'  # "PPCM" = Pied Piper Compression Magic
PP_VERSION = 1

# Tabela de quantizacao para luminancia (baseada em JPEG, ajustavel)
QUANT_LUMINANCE_BASE = np.array([
    [16, 11, 10, 16,  24,  40,  51,  61],
    [12, 12, 14, 19,  26,  58,  60,  55],
    [14, 13, 16, 24,  40,  57,  69,  56],
    [14, 17, 22, 29,  51,  87,  80,  62],
    [18, 22, 37, 56,  68, 109, 103,  77],
    [24, 35, 55, 64,  81, 104, 113,  92],
    [49, 64, 78, 87, 103, 121, 120, 101],
    [72, 92, 95, 98, 112, 100, 103,  99],
], dtype=np.float64)

# Tabela de quantizacao para crominancia
QUANT_CHROMINANCE_BASE = np.array([
    [17, 18, 24, 47, 99, 99, 99, 99],
    [18, 21, 26, 66, 99, 99, 99, 99],
    [24, 26, 56, 99, 99, 99, 99, 99],
    [47, 66, 99, 99, 99, 99, 99, 99],
    [99, 99, 99, 99, 99, 99, 99, 99],
    [99, 99, 99, 99, 99, 99, 99, 99],
    [99, 99, 99, 99, 99, 99, 99, 99],
    [99, 99, 99, 99, 99, 99, 99, 99],
], dtype=np.float64)


def _get_quant_table(base_table: np.ndarray, quality: int) -> np.ndarray:
    """Gera tabela de quantizacao ajustada pela qualidade (1-100)."""
    quality = max(1, min(100, quality))
    if quality < 50:
        scale = 5000 / quality
    else:
        scale = 200 - 2 * quality
    table = np.floor((base_table * scale + 50) / 100)
    table[table < 1] = 1
    table[table > 255] = 255
    return table


def _rgb_to_ycbcr(img_array: np.ndarray) -> np.ndarray:
    """Converte RGB para YCbCr."""
    r = img_array[:, :, 0].astype(np.float64)
    g = img_array[:, :, 1].astype(np.float64)
    b = img_array[:, :, 2].astype(np.float64)

    y  =  0.299 * r + 0.587 * g + 0.114 * b
    cb = -0.168736 * r - 0.331264 * g + 0.5 * b + 128
    cr =  0.5 * r - 0.418688 * g - 0.081312 * b + 128

    result = np.stack([y, cb, cr], axis=-1)
    return result


def _ycbcr_to_rgb(ycbcr: np.ndarray) -> np.ndarray:
    """Converte YCbCr para RGB."""
    y  = ycbcr[:, :, 0]
    cb = ycbcr[:, :, 1] - 128
    cr = ycbcr[:, :, 2] - 128

    r = y + 1.402 * cr
    g = y - 0.344136 * cb - 0.714136 * cr
    b = y + 1.772 * cb

    rgb = np.stack([r, g, b], axis=-1)
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)
    return rgb


def _subsample_420(channel: np.ndarray) -> np.ndarray:
    """Subamostragem 4:2:0 - reduz crominancia pela metade em ambas dimensoes."""
    h, w = channel.shape
    # Garante dimensoes pares
    h2 = h if h % 2 == 0 else h - 1
    w2 = w if w % 2 == 0 else w - 1
    sub = channel[:h2, :w2].reshape(h2 // 2, 2, w2 // 2, 2).mean(axis=(1, 3))
    return sub


def _upsample_420(channel: np.ndarray, target_h: int, target_w: int) -> np.ndarray:
    """Restaura crominancia subamostrada para tamanho original."""
    upsampled = np.repeat(np.repeat(channel, 2, axis=0), 2, axis=1)
    return upsampled[:target_h, :target_w]


def _dct_2d(block: np.ndarray) -> np.ndarray:
    """DCT 2D para bloco 8x8."""
    N = 8
    result = np.zeros((N, N), dtype=np.float64)
    for u in range(N):
        for v in range(N):
            cu = 1.0 / math.sqrt(2) if u == 0 else 1.0
            cv = 1.0 / math.sqrt(2) if v == 0 else 1.0
            s = 0.0
            for x in range(N):
                for y in range(N):
                    s += block[x, y] * math.cos((2 * x + 1) * u * math.pi / 16) * \
                         math.cos((2 * y + 1) * v * math.pi / 16)
            result[u, v] = 0.25 * cu * cv * s
    return result


def _idct_2d(block: np.ndarray) -> np.ndarray:
    """IDCT 2D para bloco 8x8."""
    N = 8
    result = np.zeros((N, N), dtype=np.float64)
    for x in range(N):
        for y in range(N):
            s = 0.0
            for u in range(N):
                for v in range(N):
                    cu = 1.0 / math.sqrt(2) if u == 0 else 1.0
                    cv = 1.0 / math.sqrt(2) if v == 0 else 1.0
                    s += cu * cv * block[u, v] * \
                         math.cos((2 * x + 1) * u * math.pi / 16) * \
                         math.cos((2 * y + 1) * v * math.pi / 16)
            result[x, y] = 0.25 * s
    return result


def _zigzag(block: np.ndarray) -> list:
    """Percorre bloco 8x8 em ordem zigzag."""
    indices = [
        (0,0),(0,1),(1,0),(2,0),(1,1),(0,2),(0,3),(1,2),
        (2,1),(3,0),(4,0),(3,1),(2,2),(1,3),(0,4),(0,5),
        (1,4),(2,3),(3,2),(4,1),(5,0),(6,0),(5,1),(4,2),
        (3,3),(2,4),(1,5),(0,6),(0,7),(1,6),(2,5),(3,4),
        (4,3),(5,2),(6,1),(7,0),(7,1),(6,2),(5,3),(4,4),
        (3,5),(2,6),(1,7),(2,7),(3,6),(4,5),(5,4),(6,3),
        (7,2),(7,3),(6,4),(5,5),(4,6),(3,7),(4,7),(5,6),
        (6,5),(7,4),(7,5),(6,6),(5,7),(6,7),(7,6),(7,7),
    ]
    return [int(block[i, j]) for i, j in indices]


def _unzigzag(data: list) -> np.ndarray:
    """Reconstroi bloco 8x8 a partir da ordem zigzag."""
    indices = [
        (0,0),(0,1),(1,0),(2,0),(1,1),(0,2),(0,3),(1,2),
        (2,1),(3,0),(4,0),(3,1),(2,2),(1,3),(0,4),(0,5),
        (1,4),(2,3),(3,2),(4,1),(5,0),(6,0),(5,1),(4,2),
        (3,3),(2,4),(1,5),(0,6),(0,7),(1,6),(2,5),(3,4),
        (4,3),(5,2),(6,1),(7,0),(7,1),(6,2),(5,3),(4,4),
        (3,5),(2,6),(1,7),(2,7),(3,6),(4,5),(5,4),(6,3),
        (7,2),(7,3),(6,4),(5,5),(4,6),(3,7),(4,7),(5,6),
        (6,5),(7,4),(7,5),(6,6),(5,7),(6,7),(7,6),(7,7),
    ]
    block = np.zeros((8, 8), dtype=np.float64)
    for idx, (i, j) in enumerate(indices):
        if idx < len(data):
            block[i, j] = data[idx]
    return block


def _rle_encode(data: list) -> list:
    """Run-Length Encoding otimizado para sequencias de zeros."""
    encoded = []
    i = 0
    while i < len(data):
        if data[i] == 0:
            count = 0
            while i < len(data) and data[i] == 0:
                count += 1
                i += 1
            encoded.append((0, count))
        else:
            encoded.append((data[i], 1))
            i += 1
    return encoded


def _rle_decode(encoded: list, length: int = 64) -> list:
    """Decodifica RLE."""
    data = []
    for val, count in encoded:
        data.extend([val] * count)
    # Preenche com zeros se necessario
    while len(data) < length:
        data.append(0)
    return data[:length]


def _process_channel(channel: np.ndarray, quant_table: np.ndarray) -> list:
    """Processa um canal inteiro: DCT + quantizacao + zigzag + RLE por blocos 8x8."""
    h, w = channel.shape
    # Padding para multiplo de 8
    pad_h = (8 - h % 8) % 8
    pad_w = (8 - w % 8) % 8
    padded = np.pad(channel, ((0, pad_h), (0, pad_w)), mode='edge')
    ph, pw = padded.shape

    all_blocks = []
    for i in range(0, ph, 8):
        for j in range(0, pw, 8):
            block = padded[i:i+8, j:j+8].astype(np.float64) - 128.0
            dct_block = _dct_2d(block)
            quantized = np.round(dct_block / quant_table).astype(int)
            zigzag_data = _zigzag(quantized)
            rle_data = _rle_encode(zigzag_data)
            all_blocks.append(rle_data)

    return all_blocks


def _reconstruct_channel(blocks: list, height: int, width: int,
                         quant_table: np.ndarray) -> np.ndarray:
    """Reconstroi canal a partir dos blocos comprimidos."""
    pad_h = (8 - height % 8) % 8
    pad_w = (8 - width % 8) % 8
    ph = height + pad_h
    pw = width + pad_w

    result = np.zeros((ph, pw), dtype=np.float64)
    block_idx = 0

    for i in range(0, ph, 8):
        for j in range(0, pw, 8):
            rle_data = blocks[block_idx]
            zigzag_data = _rle_decode(rle_data)
            quantized = _unzigzag(zigzag_data)
            dct_block = quantized * quant_table
            block = _idct_2d(dct_block) + 128.0
            result[i:i+8, j:j+8] = block
            block_idx += 1

    return np.clip(result[:height, :width], 0, 255)


def compress(input_path: str, output_path: str, quality: int = 75) -> Dict[str, Any]:
    """
    Comprime uma imagem para o formato .PP

    Args:
        input_path: Caminho da imagem de entrada (qualquer formato suportado pelo Pillow)
        output_path: Caminho do arquivo .PP de saida
        quality: Qualidade da compressao (1-100, padrao 75)

    Returns:
        Dicionario com estatisticas da compressao
    """
    start_time = time.time()

    # Abre a imagem
    img = Image.open(input_path)
    original_format = img.format or "UNKNOWN"
    original_mode = img.mode
    original_size_bytes = len(open(input_path, 'rb').read())

    # Converte para RGB se necessario
    if img.mode == 'RGBA':
        # Preserva canal alpha
        has_alpha = True
        alpha_channel = np.array(img)[:, :, 3]
        img = img.convert('RGB')
    elif img.mode != 'RGB':
        has_alpha = False
        img = img.convert('RGB')
    else:
        has_alpha = False

    img_array = np.array(img)
    height, width = img_array.shape[:2]
    total_pixels = height * width

    # Converte para YCbCr
    ycbcr = _rgb_to_ycbcr(img_array)

    y_channel = ycbcr[:, :, 0]
    cb_channel = ycbcr[:, :, 1]
    cr_channel = ycbcr[:, :, 2]

    # Subamostragem 4:2:0 nos canais de crominancia
    cb_sub = _subsample_420(cb_channel)
    cr_sub = _subsample_420(cr_channel)

    # Tabelas de quantizacao
    quant_y = _get_quant_table(QUANT_LUMINANCE_BASE, quality)
    quant_c = _get_quant_table(QUANT_CHROMINANCE_BASE, quality)

    # Processa cada canal
    y_blocks = _process_channel(y_channel, quant_y)
    cb_blocks = _process_channel(cb_sub, quant_c)
    cr_blocks = _process_channel(cr_sub, quant_c)

    # Canal alpha (se existir)
    alpha_blocks = None
    if has_alpha:
        quant_a = _get_quant_table(QUANT_LUMINANCE_BASE, max(quality, 90))
        alpha_blocks = _process_channel(alpha_channel.astype(np.float64), quant_a)

    # Monta os dados comprimidos
    payload = {
        'y': y_blocks,
        'cb': cb_blocks,
        'cr': cr_blocks,
        'alpha': alpha_blocks,
    }

    payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    compressed_data = zlib.compress(payload_bytes, level=9)

    # Header
    header = {
        'width': width,
        'height': height,
        'quality': quality,
        'has_alpha': has_alpha,
        'original_format': original_format,
        'original_mode': original_mode,
        'cb_shape': list(cb_sub.shape),
        'cr_shape': list(cr_sub.shape),
        'quant_y': quant_y.tolist(),
        'quant_c': quant_c.tolist(),
    }
    if has_alpha:
        header['quant_a'] = _get_quant_table(QUANT_LUMINANCE_BASE, max(quality, 90)).tolist()
        header['alpha_shape'] = [height, width]

    header_bytes = json.dumps(header, separators=(',', ':')).encode('utf-8')

    # Escreve o arquivo .PP
    with open(output_path, 'wb') as f:
        f.write(PP_MAGIC)
        f.write(struct.pack('<H', PP_VERSION))
        f.write(struct.pack('<I', len(header_bytes)))
        f.write(header_bytes)
        f.write(compressed_data)

    elapsed = time.time() - start_time
    output_size = len(PP_MAGIC) + 2 + 4 + len(header_bytes) + len(compressed_data)

    # Estatisticas
    compression_ratio = original_size_bytes / output_size if output_size > 0 else 0
    reduction_pct = (1 - output_size / original_size_bytes) * 100 if original_size_bytes > 0 else 0

    stats = {
        'input_file': input_path,
        'output_file': output_path,
        'original_format': original_format,
        'original_mode': original_mode,
        'dimensions': f'{width}x{height}',
        'total_pixels': total_pixels,
        'megapixels': round(total_pixels / 1_000_000, 2),
        'original_size_bytes': original_size_bytes,
        'original_size_human': _human_size(original_size_bytes),
        'compressed_size_bytes': output_size,
        'compressed_size_human': _human_size(output_size),
        'compression_ratio': round(compression_ratio, 2),
        'reduction_percent': round(reduction_pct, 2),
        'quality': quality,
        'has_alpha': has_alpha,
        'time_seconds': round(elapsed, 3),
        'pixels_per_second': int(total_pixels / elapsed) if elapsed > 0 else 0,
        'y_blocks': len(y_blocks),
        'cb_blocks': len(cb_blocks),
        'cr_blocks': len(cr_blocks),
        'total_blocks': len(y_blocks) + len(cb_blocks) + len(cr_blocks),
    }

    return stats


def decompress(input_path: str, output_path: str, output_format: str = None) -> Dict[str, Any]:
    """
    Descomprime um arquivo .PP para imagem.

    Args:
        input_path: Caminho do arquivo .PP
        output_path: Caminho da imagem de saida
        output_format: Formato de saida (auto-detectado pela extensao se None)

    Returns:
        Dicionario com estatisticas da descompressao
    """
    start_time = time.time()

    with open(input_path, 'rb') as f:
        # Le magic number
        magic = f.read(4)
        if magic != PP_MAGIC:
            raise ValueError(
                f"Arquivo invalido: magic number incorreto. "
                f"Esperado {PP_MAGIC!r}, recebido {magic!r}"
            )

        # Le versao
        version = struct.unpack('<H', f.read(2))[0]
        if version > PP_VERSION:
            raise ValueError(
                f"Versao do arquivo ({version}) nao suportada. "
                f"Versao maxima suportada: {PP_VERSION}"
            )

        # Le header
        header_size = struct.unpack('<I', f.read(4))[0]
        header_bytes = f.read(header_size)
        header = json.loads(header_bytes.decode('utf-8'))

        # Le dados comprimidos
        compressed_data = f.read()

    pp_file_size = len(magic) + 2 + 4 + header_size + len(compressed_data)

    # Descomprime dados
    payload_bytes = zlib.decompress(compressed_data)
    payload = json.loads(payload_bytes.decode('utf-8'))

    width = header['width']
    height = header['height']
    has_alpha = header['has_alpha']
    quant_y = np.array(header['quant_y'], dtype=np.float64)
    quant_c = np.array(header['quant_c'], dtype=np.float64)

    # Reconstroi canais
    y_channel = _reconstruct_channel(payload['y'], height, width, quant_y)
    cb_shape = header['cb_shape']
    cr_shape = header['cr_shape']
    cb_sub = _reconstruct_channel(payload['cb'], cb_shape[0], cb_shape[1], quant_c)
    cr_sub = _reconstruct_channel(payload['cr'], cr_shape[0], cr_shape[1], quant_c)

    # Upsample crominancia
    cb_full = _upsample_420(cb_sub, height, width)
    cr_full = _upsample_420(cr_sub, height, width)

    # Reconstroi YCbCr
    ycbcr = np.stack([y_channel, cb_full, cr_full], axis=-1)

    # Converte para RGB
    rgb = _ycbcr_to_rgb(ycbcr)

    # Canal alpha
    if has_alpha and payload.get('alpha') is not None:
        quant_a = np.array(header['quant_a'], dtype=np.float64)
        alpha_shape = header['alpha_shape']
        alpha = _reconstruct_channel(payload['alpha'], alpha_shape[0], alpha_shape[1], quant_a)
        alpha = np.clip(alpha, 0, 255).astype(np.uint8)
        rgba = np.dstack([rgb, alpha])
        img = Image.fromarray(rgba, 'RGBA')
    else:
        img = Image.fromarray(rgb, 'RGB')

    # Salva imagem
    img.save(output_path)

    elapsed = time.time() - start_time
    output_size = len(open(output_path, 'rb').read())
    total_pixels = width * height

    stats = {
        'input_file': input_path,
        'output_file': output_path,
        'original_format': header.get('original_format', 'UNKNOWN'),
        'dimensions': f'{width}x{height}',
        'total_pixels': total_pixels,
        'megapixels': round(total_pixels / 1_000_000, 2),
        'pp_file_size_bytes': pp_file_size,
        'pp_file_size_human': _human_size(pp_file_size),
        'restored_size_bytes': output_size,
        'restored_size_human': _human_size(output_size),
        'has_alpha': has_alpha,
        'quality': header['quality'],
        'time_seconds': round(elapsed, 3),
        'pixels_per_second': int(total_pixels / elapsed) if elapsed > 0 else 0,
    }

    return stats


def _human_size(num_bytes: int) -> str:
    """Converte bytes para formato legivel."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} TB"
