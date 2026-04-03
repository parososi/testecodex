#!/usr/bin/env python3
"""
Pied Piper CLI - Interface de linha de comando para compressao de imagens .PP

Uso:
  python -m pied_piper compress <imagem> [-o saida.PP] [-q qualidade]
  python -m pied_piper decompress <arquivo.PP> [-o saida.png]
  python -m pied_piper info <arquivo.PP>
"""

import argparse
import os
import sys

from pied_piper.codec import compress, decompress, PP_MAGIC, PP_VERSION
from pied_piper import __version__


BANNER = r"""
  ____  _          _   ____  _
 |  _ \(_) ___  __| | |  _ \(_)_ __   ___ _ __
 | |_) | |/ _ \/ _` | | |_) | | '_ \ / _ \ '__|
 |  __/| |  __/ (_| | |  __/| | |_) |  __/ |
 |_|   |_|\___|\__,_| |_|   |_| .__/ \___|_|
                               |_|
  Compressor de Imagens v{version}
  "Making the world a better place... through compression"
""".format(version=__version__)


def _print_stats_compress(stats: dict):
    """Exibe estatisticas formatadas da compressao."""
    print("\n" + "=" * 60)
    print("  PIED PIPER - ESTATISTICAS DE COMPRESSAO")
    print("=" * 60)
    print(f"  Arquivo de entrada:    {stats['input_file']}")
    print(f"  Arquivo de saida:      {stats['output_file']}")
    print(f"  Formato original:      {stats['original_format']}")
    print(f"  Modo de cor original:  {stats['original_mode']}")
    print("-" * 60)
    print(f"  Dimensoes:             {stats['dimensions']}")
    print(f"  Total de pixels:       {stats['total_pixels']:,}")
    print(f"  Megapixels:            {stats['megapixels']} MP")
    print(f"  Canal Alpha:           {'Sim' if stats['has_alpha'] else 'Nao'}")
    print("-" * 60)
    print(f"  Tamanho original:      {stats['original_size_human']}")
    print(f"  Tamanho comprimido:    {stats['compressed_size_human']}")
    print(f"  Taxa de compressao:    {stats['compression_ratio']}:1")

    reduction = stats['reduction_percent']
    if reduction > 0:
        bar_len = int(min(reduction, 100) / 2)
        bar = '#' * bar_len + '-' * (50 - bar_len)
        print(f"  Reducao:               {reduction}%")
        print(f"  [{bar}]")
    else:
        print(f"  Reducao:               {reduction}% (arquivo aumentou)")

    print("-" * 60)
    print(f"  Qualidade:             {stats['quality']}")
    print(f"  Blocos processados:    {stats['total_blocks']:,}")
    print(f"    - Luminancia (Y):    {stats['y_blocks']:,}")
    print(f"    - Crominancia (Cb):  {stats['cb_blocks']:,}")
    print(f"    - Crominancia (Cr):  {stats['cr_blocks']:,}")
    print("-" * 60)
    print(f"  Tempo de compressao:   {stats['time_seconds']}s")
    print(f"  Velocidade:            {stats['pixels_per_second']:,} pixels/s")
    print("=" * 60)
    print(f"  Arquivo .PP salvo com sucesso!")
    print("=" * 60 + "\n")


def _print_stats_decompress(stats: dict):
    """Exibe estatisticas formatadas da descompressao."""
    print("\n" + "=" * 60)
    print("  PIED PIPER - ESTATISTICAS DE DESCOMPRESSAO")
    print("=" * 60)
    print(f"  Arquivo de entrada:    {stats['input_file']}")
    print(f"  Arquivo de saida:      {stats['output_file']}")
    print(f"  Formato original:      {stats['original_format']}")
    print("-" * 60)
    print(f"  Dimensoes:             {stats['dimensions']}")
    print(f"  Total de pixels:       {stats['total_pixels']:,}")
    print(f"  Megapixels:            {stats['megapixels']} MP")
    print(f"  Canal Alpha:           {'Sim' if stats['has_alpha'] else 'Nao'}")
    print("-" * 60)
    print(f"  Tamanho .PP:           {stats['pp_file_size_human']}")
    print(f"  Tamanho restaurado:    {stats['restored_size_human']}")
    print(f"  Qualidade usada:       {stats['quality']}")
    print("-" * 60)
    print(f"  Tempo de descompressao: {stats['time_seconds']}s")
    print(f"  Velocidade:            {stats['pixels_per_second']:,} pixels/s")
    print("=" * 60)
    print(f"  Imagem restaurada com sucesso!")
    print("=" * 60 + "\n")


def _print_info(input_path: str):
    """Exibe informacoes de um arquivo .PP sem descomprimir."""
    import struct
    import json

    with open(input_path, 'rb') as f:
        magic = f.read(4)
        if magic != PP_MAGIC:
            print(f"  ERRO: '{input_path}' nao e um arquivo .PP valido.")
            sys.exit(1)

        version = struct.unpack('<H', f.read(2))[0]
        header_size = struct.unpack('<I', f.read(4))[0]
        header_bytes = f.read(header_size)
        header = json.loads(header_bytes.decode('utf-8'))
        remaining = len(f.read())

    file_size = os.path.getsize(input_path)

    print("\n" + "=" * 60)
    print("  PIED PIPER - INFORMACOES DO ARQUIVO .PP")
    print("=" * 60)
    print(f"  Arquivo:               {input_path}")
    print(f"  Tamanho:               {file_size:,} bytes")
    print(f"  Versao PP:             {version}")
    print(f"  Tamanho do header:     {header_size:,} bytes")
    print(f"  Dados comprimidos:     {remaining:,} bytes")
    print("-" * 60)
    print(f"  Dimensoes:             {header['width']}x{header['height']}")
    print(f"  Pixels:                {header['width'] * header['height']:,}")
    print(f"  Qualidade:             {header['quality']}")
    print(f"  Canal Alpha:           {'Sim' if header['has_alpha'] else 'Nao'}")
    print(f"  Formato original:      {header.get('original_format', 'N/A')}")
    print(f"  Modo original:         {header.get('original_mode', 'N/A')}")
    print("=" * 60 + "\n")


def cmd_compress(args):
    """Comando de compressao."""
    input_path = args.input

    if not os.path.exists(input_path):
        print(f"  ERRO: Arquivo '{input_path}' nao encontrado.")
        sys.exit(1)

    if args.output:
        output_path = args.output
    else:
        base = os.path.splitext(input_path)[0]
        output_path = base + '.PP'

    quality = args.quality

    print(BANNER)
    print(f"  Comprimindo: {input_path}")
    print(f"  Qualidade:   {quality}")
    print(f"  Saida:       {output_path}")
    print("  Processando...\n")

    try:
        stats = compress(input_path, output_path, quality)
        _print_stats_compress(stats)
    except Exception as e:
        print(f"\n  ERRO durante compressao: {e}")
        sys.exit(1)


def cmd_decompress(args):
    """Comando de descompressao."""
    input_path = args.input

    if not os.path.exists(input_path):
        print(f"  ERRO: Arquivo '{input_path}' nao encontrado.")
        sys.exit(1)

    if args.output:
        output_path = args.output
    else:
        base = os.path.splitext(input_path)[0]
        output_path = base + '_restored.png'

    print(BANNER)
    print(f"  Descomprimindo: {input_path}")
    print(f"  Saida:          {output_path}")
    print("  Processando...\n")

    try:
        stats = decompress(input_path, output_path)
        _print_stats_decompress(stats)
    except Exception as e:
        print(f"\n  ERRO durante descompressao: {e}")
        sys.exit(1)


def cmd_info(args):
    """Comando de informacoes."""
    input_path = args.input

    if not os.path.exists(input_path):
        print(f"  ERRO: Arquivo '{input_path}' nao encontrado.")
        sys.exit(1)

    print(BANNER)
    _print_info(input_path)


def main():
    parser = argparse.ArgumentParser(
        prog='pied_piper',
        description='Pied Piper - O compressor de imagens mais eficiente da Internet',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=BANNER,
    )
    parser.add_argument('--version', action='version', version=f'Pied Piper v{__version__}')

    subparsers = parser.add_subparsers(dest='command', help='Comandos disponiveis')

    # Compress
    p_compress = subparsers.add_parser('compress', help='Comprimir uma imagem para .PP')
    p_compress.add_argument('input', help='Caminho da imagem de entrada')
    p_compress.add_argument('-o', '--output', help='Caminho do arquivo .PP de saida')
    p_compress.add_argument('-q', '--quality', type=int, default=75,
                            help='Qualidade (1-100, padrao: 75)')
    p_compress.set_defaults(func=cmd_compress)

    # Decompress
    p_decompress = subparsers.add_parser('decompress', help='Descomprimir um arquivo .PP')
    p_decompress.add_argument('input', help='Caminho do arquivo .PP')
    p_decompress.add_argument('-o', '--output', help='Caminho da imagem de saida')
    p_decompress.set_defaults(func=cmd_decompress)

    # Info
    p_info = subparsers.add_parser('info', help='Exibir informacoes de um arquivo .PP')
    p_info.add_argument('input', help='Caminho do arquivo .PP')
    p_info.set_defaults(func=cmd_info)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == '__main__':
    main()
