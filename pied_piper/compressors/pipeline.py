"""
Pipeline Universal de Compressao - Pied Piper

Inspirado no 7-Zip (Igor Pavlov) e WinRAR (Eugene Roshal):
  - 7-Zip usa LZMA/LZMA2 com filtros de pre-processamento (Delta, BCJ)
  - WinRAR usa combinacao de LZ77 + PPM + filtros (Delta, Audio, Color)

Este pipeline testa multiplas estrategias e escolhe a que produz
o menor resultado, garantindo SEMPRE compressao sem perdas (lossless).

Estrategias:
  1. LZMA       - Algoritmo do 7-Zip, melhor compressao geral
  2. BZ2        - Burrows-Wheeler (bzip2), otimo para texto
  3. DEFLATE    - zlib nivel 9, rapido e universal
  4. BWT+MTF    - Nosso BWT + Move-to-Front + zlib
  5. DELTA+LZMA - Delta pre-processing + LZMA (para dados sequenciais)
  6. STORED     - Dados sem compressao (se nenhum metodo reduz)

O pipeline testa TODAS as estrategias e empacota com a menor.
"""

import bz2
import hashlib
import lzma
import struct
import zlib

from pied_piper.compressors.bwt import bwt_compress, bwt_decompress
from pied_piper.compressors.delta import delta_compress, delta_decompress

# Identificadores de estrategia
STRATEGY_LZMA = 1
STRATEGY_BZ2 = 2
STRATEGY_DEFLATE = 3
STRATEGY_BWT = 4
STRATEGY_DELTA_LZMA = 5
STRATEGY_STORED = 0

STRATEGY_NAMES = {
    STRATEGY_STORED: 'stored',
    STRATEGY_LZMA: 'lzma',
    STRATEGY_BZ2: 'bz2',
    STRATEGY_DEFLATE: 'deflate',
    STRATEGY_BWT: 'bwt',
    STRATEGY_DELTA_LZMA: 'delta+lzma',
}

# Magic bytes para o formato universal
PP_UNIVERSAL_MAGIC = b'PPUF'  # Pied Piper Universal Format

# Tamanho maximo para BWT (evita lentidao em arquivos grandes)
BWT_MAX_SIZE = 2 * 1024 * 1024  # 2 MB


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _try_lzma(data: bytes) -> bytes:
    """Comprime com LZMA (algoritmo do 7-Zip)."""
    # Preset 9 = maxima compressao (equivalente ao 7-Zip Ultra)
    return lzma.compress(data, preset=9 | lzma.PRESET_EXTREME)


def _try_bz2(data: bytes) -> bytes:
    """Comprime com BZ2 (Burrows-Wheeler do bzip2)."""
    return bz2.compress(data, compresslevel=9)


def _try_deflate(data: bytes) -> bytes:
    """Comprime com DEFLATE nivel 9 (zlib)."""
    return zlib.compress(data, level=9)


def _try_bwt(data: bytes) -> bytes:
    """Comprime com nosso BWT + MTF + zlib."""
    bwt_data = bwt_compress(data)
    return zlib.compress(bwt_data, level=9)


def _try_delta_lzma(data: bytes) -> bytes:
    """Pre-processamento Delta + LZMA (inspirado filtro Delta do 7-Zip)."""
    delta_data = delta_compress(data)
    return lzma.compress(delta_data, preset=9 | lzma.PRESET_EXTREME)


def compress_universal(data: bytes) -> tuple:
    """
    Comprime dados usando a melhor estrategia disponivel.

    Testa LZMA, BZ2, DEFLATE, BWT+MTF, e Delta+LZMA, depois
    escolhe a que produz o menor resultado.

    Retorna (compressed_bytes, stats_dict)

    Formato do compressed_bytes:
      [4 bytes: PPUF magic]
      [1 byte:  estrategia usada]
      [32 bytes: SHA-256 do original]
      [8 bytes: tamanho original LE]
      [8 bytes: tamanho comprimido LE]
      [N bytes: dados comprimidos]
    """
    if not data:
        return (PP_UNIVERSAL_MAGIC + b'\x00' +
                b'0' * 64 + struct.pack('<QQ', 0, 0)), {
            'strategy': STRATEGY_STORED,
            'strategy_name': 'stored',
            'original_size': 0,
            'compressed_size': 0,
            'ratio': 1.0,
            'reduction_percent': 0.0,
        }

    original_hash = _sha256(data).encode('ascii')
    original_size = len(data)

    # Testa todas as estrategias
    candidates = {}

    # 1. LZMA (7-Zip) - melhor compressao geral
    try:
        candidates[STRATEGY_LZMA] = _try_lzma(data)
    except Exception:
        pass

    # 2. BZ2 (bzip2) - otimo para texto
    try:
        candidates[STRATEGY_BZ2] = _try_bz2(data)
    except Exception:
        pass

    # 3. DEFLATE (zlib) - rapido, baseline
    try:
        candidates[STRATEGY_DEFLATE] = _try_deflate(data)
    except Exception:
        pass

    # 4. BWT + MTF + zlib (nosso engine customizado)
    if original_size <= BWT_MAX_SIZE:
        try:
            candidates[STRATEGY_BWT] = _try_bwt(data)
        except Exception:
            pass

    # 5. Delta + LZMA (para dados com padroes sequenciais)
    try:
        candidates[STRATEGY_DELTA_LZMA] = _try_delta_lzma(data)
    except Exception:
        pass

    if not candidates:
        # Nenhuma estrategia funcionou: stored
        best_strategy = STRATEGY_STORED
        best_data = data
    else:
        # Escolhe a menor
        best_strategy = min(candidates, key=lambda k: len(candidates[k]))
        best_data = candidates[best_strategy]

        # Se a compressao nao reduziu, usa stored
        if len(best_data) >= original_size:
            best_strategy = STRATEGY_STORED
            best_data = data

    compressed_size = len(best_data)

    # Empacota
    # Hash SHA-256 hex = 64 bytes ASCII
    assert len(original_hash) == 64, f"Hash deve ter 64 bytes, tem {len(original_hash)}"
    out = bytearray()
    out += PP_UNIVERSAL_MAGIC
    out.append(best_strategy)
    out += original_hash          # 64 bytes ASCII
    out += struct.pack('<QQ', original_size, compressed_size)
    out += best_data

    ratio = original_size / compressed_size if compressed_size > 0 else 0
    reduction = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0

    stats = {
        'strategy': best_strategy,
        'strategy_name': STRATEGY_NAMES.get(best_strategy, 'unknown'),
        'original_size': original_size,
        'compressed_size': compressed_size,
        'ratio': round(ratio, 2),
        'reduction_percent': round(reduction, 2),
        'hash': original_hash.decode('ascii'),
        'all_results': {
            STRATEGY_NAMES.get(k, 'unknown'): len(v)
            for k, v in candidates.items()
        },
    }

    return bytes(out), stats


def decompress_universal(data: bytes) -> tuple:
    """
    Descomprime dados produzidos por compress_universal.

    Retorna (original_bytes, stats_dict)
    Verifica integridade via SHA-256.
    """
    # Header: 4 magic + 1 strategy + 64 hash + 16 sizes = 85 bytes
    if len(data) < 4 + 1 + 64 + 16:
        raise ValueError("Dados corrompidos: header muito curto")

    magic = data[:4]
    if magic != PP_UNIVERSAL_MAGIC:
        raise ValueError(f"Magic invalido: esperado {PP_UNIVERSAL_MAGIC!r}, recebido {magic!r}")

    strategy = data[4]
    stored_hash = data[5:69].decode('ascii')  # 64 bytes SHA-256 hex
    original_size, compressed_size = struct.unpack('<QQ', data[69:85])

    payload = data[85:85 + compressed_size]

    # Descomprime conforme a estrategia
    if strategy == STRATEGY_STORED:
        result = payload

    elif strategy == STRATEGY_LZMA:
        result = lzma.decompress(payload)

    elif strategy == STRATEGY_BZ2:
        result = bz2.decompress(payload)

    elif strategy == STRATEGY_DEFLATE:
        result = zlib.decompress(payload)

    elif strategy == STRATEGY_BWT:
        bwt_data = zlib.decompress(payload)
        result = bwt_decompress(bwt_data)

    elif strategy == STRATEGY_DELTA_LZMA:
        delta_data = lzma.decompress(payload)
        result = delta_decompress(delta_data)

    else:
        raise ValueError(f"Estrategia desconhecida: {strategy}")

    # Verifica integridade
    actual_hash = _sha256(result)
    integrity_ok = (actual_hash == stored_hash)

    if not integrity_ok:
        raise ValueError(
            f"Integridade falhou! SHA-256 esperado: {stored_hash}, "
            f"obtido: {actual_hash}"
        )

    stats = {
        'strategy': strategy,
        'strategy_name': STRATEGY_NAMES.get(strategy, 'unknown'),
        'original_size': original_size,
        'compressed_size': compressed_size,
        'integrity_verified': integrity_ok,
        'hash': stored_hash,
    }

    return result, stats
