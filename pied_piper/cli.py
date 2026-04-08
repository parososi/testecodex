"""
Pied Piper CLI - Interface de linha de comando ultra-simples.

Comandos:
    pp c <imagem> [-q 75]      Comprimir imagem para .PP
    pp d <arquivo.PP>          Descomprimir .PP para PNG
    pp i <arquivo.PP>          Mostrar informacoes do .PP
    pp engine                  Status do motor de compressao
    pp help                    Mostrar ajuda
"""

import os
import sys

from pied_piper import __version__
from pied_piper.codec import (
    compress, decompress, info, engine_info, PP_EXTENSION
)


BANNER = r"""
   ____  _          _   ____  _
  |  _ \(_) ___  __| | |  _ \(_)_ __   ___ _ __
  | |_) | |/ _ \/ _` | | |_) | | '_ \ / _ \ '__|
  |  __/| |  __/ (_| | |  __/| | |_) |  __/ |
  |_|   |_|\___|\__,_| |_|   |_| .__/ \___|_|
                                |_|
""" + f"   Middle-Out Compression Engine v{__version__}\n"


def _human(n: int) -> str:
    """Formata bytes para humanos."""
    for u in ['B', 'KB', 'MB', 'GB', 'TB']:
        if n < 1024:
            return f"{n:.2f} {u}"
        n /= 1024
    return f"{n:.2f} PB"


def _bar(percent: float, width: int = 40) -> str:
    """Gera barra de progresso."""
    p = max(0.0, min(100.0, percent))
    filled = int(p / 100 * width)
    return '[' + '#' * filled + '-' * (width - filled) + ']'


def _print_compress_stats(s: dict) -> None:
    """Mostra estatisticas detalhadas da compressao."""
    print()
    print("=" * 64)
    print("         PIED PIPER - COMPRESSAO CONCLUIDA")
    print("=" * 64)
    print(f"  Entrada:              {s['input_file']}")
    print(f"  Saida:                {s['output_file']}")
    print(f"  Formato original:     {s['original_format']} ({s['original_mode']})")
    print("-" * 64)
    print(f"  Dimensoes:            {s['width']} x {s['height']} pixels")
    print(f"  Total de pixels:      {s['total_pixels']:,}")
    print(f"  Megapixels:           {s['megapixels']} MP")
    print(f"  Canal Alpha:          {'Sim' if s['has_alpha'] else 'Nao'}")
    print("-" * 64)
    print(f"  Tamanho original:     {_human(s['original_size'])}")
    print(f"  Tamanho comprimido:   {_human(s['compressed_size'])}")
    print(f"  Taxa de compressao:   {s['compression_ratio']}:1")
    print(f"  Bits por pixel:       {s['bits_per_pixel']}")
    print()
    r = s['reduction_percent']
    if r > 0:
        print(f"  Reducao:              {r}%  {_bar(r)}")
    else:
        print(f"  Reducao:              {r}% (arquivo aumentou)")
    print("-" * 64)
    print("         ALGORITMO MIDDLE-OUT - ESTATISTICAS")
    print("-" * 64)
    print(f"  Qualidade:            {s['quality']}/100")
    print(f"  Blocos processados:   {s['total_blocks']:,}")
    print(f"  Blocos preditos:      {s['predicted_blocks']:,} "
          f"({s['prediction_percent']}%)")
    print(f"  Blocos vazios:        {s['zero_blocks']:,} "
          f"({s['zero_blocks_percent']}%)")
    print(f"  Esparsidade DCT:      {s['coefficient_sparsity']}%")
    print("-" * 64)
    print(f"  Tempo:                {s['time_seconds']}s")
    print(f"  Throughput:           {s['pixels_per_second']:,} px/s")
    print("=" * 64)
    print()


def _print_decompress_stats(s: dict) -> None:
    print()
    print("=" * 64)
    print("         PIED PIPER - DESCOMPRESSAO CONCLUIDA")
    print("=" * 64)
    print(f"  Entrada:              {s['input_file']}")
    print(f"  Saida:                {s['output_file']}")
    print(f"  Formato original:     {s['original_format']}")
    print("-" * 64)
    print(f"  Dimensoes:            {s['width']} x {s['height']} pixels")
    print(f"  Total de pixels:      {s['total_pixels']:,}")
    print(f"  Megapixels:           {s['megapixels']} MP")
    print(f"  Canal Alpha:          {'Sim' if s['has_alpha'] else 'Nao'}")
    print("-" * 64)
    print(f"  Tamanho .PP:          {_human(s['pp_size'])}")
    print(f"  Tamanho restaurado:   {_human(s['restored_size'])}")
    print(f"  Qualidade usada:      {s['quality']}/100")
    print("-" * 64)
    print(f"  Tempo:                {s['time_seconds']}s")
    print(f"  Throughput:           {s['pixels_per_second']:,} px/s")
    print("=" * 64)
    print()


def _print_info(i: dict) -> None:
    print()
    print("=" * 64)
    print("              PIED PIPER - INFO DO ARQUIVO .PP")
    print("=" * 64)
    print(f"  Arquivo:              {i['file']}")
    print(f"  Tamanho total:        {_human(i['file_size'])}")
    print(f"  Versao do formato:    {i['version']}")
    print(f"  Header:               {_human(i['header_size'])}")
    print(f"  Dados comprimidos:    {_human(i['data_size'])}")
    print("-" * 64)
    print(f"  Dimensoes:            {i['width']} x {i['height']}")
    print(f"  Total pixels:         {i['total_pixels']:,}")
    print(f"  Qualidade:            {i['quality']}/100")
    print(f"  Canal Alpha:          {'Sim' if i['has_alpha'] else 'Nao'}")
    print(f"  Formato original:     {i['original_format']} ({i['original_mode']})")
    print("=" * 64)
    print()


def _print_engine() -> None:
    e = engine_info()
    print()
    print("=" * 64)
    print("           PIED PIPER - MOTOR DE COMPRESSAO")
    print("=" * 64)
    print(f"  Motor:                {e['engine']}")
    print(f"  C engine disponivel:  "
          f"{'Sim' if e['c_engine_available'] else 'Nao'}")
    print(f"  Biblioteca:           {e['library_path']}")
    print(f"  Versao Python:        {__version__}")
    print("=" * 64)
    print()


def _print_help() -> None:
    print(BANNER)
    print("  USO SIMPLES:")
    print()
    print("    pp c <imagem> [-q QUALIDADE]    Comprime imagem -> .PP")
    print("    pp d <arquivo.PP> [-o SAIDA]    Descomprime .PP -> imagem")
    print("    pp i <arquivo.PP>               Mostra info do .PP")
    print("    pp engine                       Status do motor")
    print("    pp help                         Mostra esta ajuda")
    print("    pp version                      Versao")
    print()
    print("  COMANDOS COMPLETOS (aliases):")
    print()
    print("    pp compress <imagem>            = pp c")
    print("    pp decompress <arquivo.PP>      = pp d")
    print("    pp info <arquivo.PP>            = pp i")
    print()
    print("  EXEMPLOS:")
    print()
    print("    pp c foto.jpg                   Comprime foto.jpg -> foto.PP")
    print("    pp c foto.png -q 90             Compressao alta qualidade")
    print("    pp c foto.bmp -q 50 -o out.PP   Saida customizada")
    print("    pp d foto.PP                    Descomprime -> foto_restored.png")
    print("    pp d foto.PP -o saida.jpg       Saida JPG")
    print("    pp i foto.PP                    Ver metadados")
    print()
    print("  FORMATOS SUPORTADOS (entrada):")
    print()
    print("    PNG, JPEG, BMP, TIFF, GIF, WEBP, ICO, TGA, PPM, PGM,")
    print("    PCX, PSD, DDS, APNG, JP2, e muitos outros (via Pillow)")
    print()
    print("  QUALIDADE:")
    print()
    print("     1-30  = Maxima compressao (baixa qualidade)")
    print("    31-60  = Balanceado")
    print("    61-80  = Alta qualidade (padrao: 75)")
    print("    81-100 = Quase sem perdas")
    print()


def _parse_quality(args: list) -> int:
    """Extrai -q/--quality dos args."""
    quality = 75
    for i, a in enumerate(args):
        if a in ('-q', '--quality') and i + 1 < len(args):
            try:
                quality = int(args[i + 1])
            except ValueError:
                print(f"  ERRO: Qualidade invalida: {args[i + 1]}")
                sys.exit(1)
    return quality


def _parse_output(args: list) -> str:
    """Extrai -o/--output dos args."""
    for i, a in enumerate(args):
        if a in ('-o', '--output') and i + 1 < len(args):
            return args[i + 1]
    return None


def _get_positional(args: list) -> list:
    """Remove flags e retorna apenas argumentos posicionais."""
    positional = []
    skip_next = False
    for a in args:
        if skip_next:
            skip_next = False
            continue
        if a in ('-q', '--quality', '-o', '--output'):
            skip_next = True
            continue
        if a.startswith('-'):
            continue
        positional.append(a)
    return positional


def cmd_compress(args: list) -> int:
    positional = _get_positional(args)
    if not positional:
        print("  ERRO: Informe a imagem a ser comprimida.")
        print("  Uso: pp c <imagem> [-q QUALIDADE] [-o SAIDA]")
        return 1

    input_path = positional[0]
    quality = _parse_quality(args)
    output_path = _parse_output(args)

    if not os.path.exists(input_path):
        print(f"  ERRO: Arquivo nao encontrado: {input_path}")
        return 1

    if not 1 <= quality <= 100:
        print(f"  ERRO: Qualidade deve estar entre 1 e 100 (recebido: {quality})")
        return 1

    print(BANNER)
    print(f"  Comprimindo:  {input_path}")
    print(f"  Qualidade:    {quality}/100")
    print(f"  Algoritmo:    Middle-Out Compression (C engine)")
    print("  Processando...")

    try:
        stats = compress(input_path, output_path, quality)
        _print_compress_stats(stats)
        return 0
    except Exception as e:
        print(f"\n  ERRO: {e}")
        import traceback
        traceback.print_exc()
        return 1


def cmd_decompress(args: list) -> int:
    positional = _get_positional(args)
    if not positional:
        print("  ERRO: Informe o arquivo .PP a descomprimir.")
        print("  Uso: pp d <arquivo.PP> [-o SAIDA]")
        return 1

    input_path = positional[0]
    output_path = _parse_output(args)

    if not os.path.exists(input_path):
        print(f"  ERRO: Arquivo nao encontrado: {input_path}")
        return 1

    print(BANNER)
    print(f"  Descomprimindo: {input_path}")
    print("  Processando...")

    try:
        stats = decompress(input_path, output_path)
        _print_decompress_stats(stats)
        return 0
    except Exception as e:
        print(f"\n  ERRO: {e}")
        import traceback
        traceback.print_exc()
        return 1


def cmd_info(args: list) -> int:
    positional = _get_positional(args)
    if not positional:
        print("  ERRO: Informe o arquivo .PP")
        print("  Uso: pp i <arquivo.PP>")
        return 1

    input_path = positional[0]
    if not os.path.exists(input_path):
        print(f"  ERRO: Arquivo nao encontrado: {input_path}")
        return 1

    print(BANNER)
    try:
        _print_info(info(input_path))
        return 0
    except Exception as e:
        print(f"\n  ERRO: {e}")
        return 1


def cmd_engine(args: list) -> int:
    print(BANNER)
    _print_engine()
    return 0


def cmd_version(args: list) -> int:
    print(f"Pied Piper v{__version__}")
    return 0


def cmd_help(args: list) -> int:
    _print_help()
    return 0


# Mapa de comandos (incluindo aliases simples)
COMMANDS = {
    'c': cmd_compress,       'compress': cmd_compress,     'comp': cmd_compress,
    'd': cmd_decompress,     'decompress': cmd_decompress, 'decomp': cmd_decompress,
    'x': cmd_decompress,     'extract': cmd_decompress,
    'i': cmd_info,           'info': cmd_info,
    'engine': cmd_engine,
    'version': cmd_version,  '-v': cmd_version,     '--version': cmd_version,
    'help': cmd_help,        '-h': cmd_help,        '--help': cmd_help,
}


def main(argv: list = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        _print_help()
        return 0

    cmd = argv[0].lower()
    args = argv[1:]

    if cmd not in COMMANDS:
        print(f"  ERRO: Comando desconhecido: {cmd}")
        print("  Use 'pp help' para ver comandos disponiveis.")
        return 1

    return COMMANDS[cmd](args)


if __name__ == '__main__':
    sys.exit(main())
