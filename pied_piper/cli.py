"""
Pied Piper CLI - Interface de linha de comando ultra-simples.

Comandos:
    pp c <imagem> [-q 75] [-l]  Comprimir imagem para .PP
    pp d <arquivo.PP>            Descomprimir .PP para PNG
    pp i <arquivo.PP>            Mostrar informacoes do .PP
    pp engine                    Status do motor de compressao
    pp verify <img> <pp>         Verificar integridade lossless
    pp help                      Mostrar ajuda
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
""" + f"   Middle-Out Lossless/Lossy Engine v{__version__}\n"


def _human(n: int) -> str:
    """Formata bytes para humanos."""
    for u in ['B', 'KB', 'MB', 'GB', 'TB']:
        if n < 1024:
            return f"{n:.2f} {u}"
        n /= 1024
    return f"{n:.2f} PB"


def _bar(percent: float, width: int = 36) -> str:
    """Gera barra de progresso."""
    p = max(0.0, min(100.0, percent))
    filled = int(p / 100 * width)
    return '[' + '#' * filled + '.' * (width - filled) + ']'


def _mode_badge(lossless: bool) -> str:
    return '[ SEM PERDAS ]' if lossless else '[   LOSSY    ]'


def _print_compress_stats(s: dict) -> None:
    """Mostra estatisticas detalhadas da compressao."""
    lossless = s.get('lossless', False)
    W = 66
    print()
    print("=" * W)
    print(f"   PIED PIPER - COMPRESSAO CONCLUIDA  {_mode_badge(lossless)}")
    print("=" * W)
    print(f"  Entrada:              {s['input_file']}")
    print(f"  Saida:                {s['output_file']}")
    print(f"  Formato original:     {s['original_format']} ({s['original_mode']})")
    print("-" * W)
    print(f"  Dimensoes:            {s['width']} x {s['height']} pixels")
    print(f"  Total de pixels:      {s['total_pixels']:,}")
    print(f"  Megapixels:           {s['megapixels']} MP")
    print(f"  Canal Alpha:          {'Sim' if s['has_alpha'] else 'Nao'}")
    print("-" * W)
    print(f"  Tamanho original:     {_human(s['original_size'])}")
    print(f"  Tamanho comprimido:   {_human(s['compressed_size'])}")
    print(f"  Taxa de compressao:   {s['compression_ratio']}:1")
    print(f"  Bits por pixel:       {s['bits_per_pixel']}")
    r = s['reduction_percent']
    label = f"{r}%" if r >= 0 else f"{r}% (arquivo cresceu)"
    print(f"  Reducao:              {label}")
    if r > 0:
        print(f"                        {_bar(r)}")
    print("-" * W)
    print("    ALGORITMO MIDDLE-OUT - ESTATISTICAS INTERNAS")
    print("-" * W)
    if lossless:
        print(f"  Modo:                 LOSSLESS - RCT + DPCM espiral")
        print(f"  Transformada cor:     RCT JPEG 2000 reversivel (Y, Cb, Cr)")
        print(f"  PSNR:                 {s['psnr_str']}")
    else:
        print(f"  Modo:                 LOSSY - DCT + Quantizacao adaptativa")
        print(f"  Qualidade:            {s['quality']}/100")
        print(f"  PSNR:                 {s['psnr_str']}")
    print(f"  Blocos processados:   {s['total_blocks']:,}")
    print(f"  Blocos preditos:      {s['predicted_blocks']:,} "
          f"({s['prediction_percent']}%)")
    if not lossless:
        print(f"  Blocos vazios:        {s['zero_blocks']:,} "
              f"({s['zero_blocks_percent']}%)")
    print(f"  Esparsidade residual: {s['coefficient_sparsity']}%")
    print("-" * W)
    print(f"  Tempo:                {s['time_seconds']}s")
    print(f"  Throughput:           {s['pixels_per_second']:,} px/s")
    print("=" * W)
    print()


def _print_decompress_stats(s: dict) -> None:
    lossless = s.get('lossless', False)
    W = 66
    print()
    print("=" * W)
    print(f"   PIED PIPER - DESCOMPRESSAO CONCLUIDA  {_mode_badge(lossless)}")
    print("=" * W)
    print(f"  Entrada:              {s['input_file']}")
    print(f"  Saida:                {s['output_file']}")
    print(f"  Formato original:     {s['original_format']}")
    print("-" * W)
    print(f"  Dimensoes:            {s['width']} x {s['height']} pixels")
    print(f"  Total de pixels:      {s['total_pixels']:,}")
    print(f"  Megapixels:           {s['megapixels']} MP")
    print(f"  Canal Alpha:          {'Sim' if s['has_alpha'] else 'Nao'}")
    print("-" * W)
    print(f"  Tamanho .PP:          {_human(s['pp_size'])}")
    print(f"  Tamanho restaurado:   {_human(s['restored_size'])}")
    if lossless:
        print(f"  PSNR:                 {s['psnr_str']}")
        v = s.get('integrity_verified')
        if v is True:
            print(f"  Integridade SHA-256:  VERIFICADA - pixels identicos ao original")
        elif v is False:
            print(f"  Integridade SHA-256:  FALHOU - dados corrompidos!")
        else:
            print(f"  Integridade SHA-256:  hash original nao disponivel")
    else:
        print(f"  Qualidade usada:      {s['quality']}/100")
        print(f"  PSNR:                 {s['psnr_str']}")
    print("-" * W)
    print(f"  Tempo:                {s['time_seconds']}s")
    print(f"  Throughput:           {s['pixels_per_second']:,} px/s")
    print("=" * W)
    print()


def _print_info(i: dict) -> None:
    W = 66
    lossless = i.get('lossless', False)
    print()
    print("=" * W)
    print(f"          PIED PIPER - INFO DO ARQUIVO .PP  {_mode_badge(lossless)}")
    print("=" * W)
    print(f"  Arquivo:              {i['file']}")
    print(f"  Tamanho total:        {_human(i['file_size'])}")
    print(f"  Versao do formato:    {i['version']}")
    print(f"  Header:               {_human(i['header_size'])}")
    print(f"  Dados comprimidos:    {_human(i['data_size'])}")
    print("-" * W)
    print(f"  Dimensoes:            {i['width']} x {i['height']}")
    print(f"  Total pixels:         {i['total_pixels']:,}")
    print(f"  Modo:                 {'LOSSLESS (sem perdas)' if lossless else 'LOSSY'}")
    print(f"  Qualidade gravada:    {i['quality']}/100")
    print(f"  Canal Alpha:          {'Sim' if i['has_alpha'] else 'Nao'}")
    print(f"  Formato original:     {i['original_format']} ({i['original_mode']})")
    print("=" * W)
    print()


def _print_engine() -> None:
    e = engine_info()
    W = 66
    print()
    print("=" * W)
    print("              PIED PIPER - MOTOR DE COMPRESSAO")
    print("=" * W)
    print(f"  Motor C:              {e['engine']}")
    print(f"  C engine disponivel:  "
          f"{'Sim' if e['c_engine_available'] else 'Nao'}")
    print(f"  Modo lossless:        "
          f"{'Disponivel' if e.get('lossless_available') else 'Indisponivel'}")
    print(f"  Biblioteca:           {e['library_path']}")
    print(f"  Linguagens:           {e.get('languages', 'N/A')}")
    print(f"  Versao formato .PP:   v{e.get('format_version', '?')}")
    print(f"  Versao Pied Piper:    {__version__}")
    print("=" * W)
    print()


def _print_help() -> None:
    print(BANNER)
    print("  USO SIMPLES:")
    print()
    print("    pp c <imagem> [-q Q] [-l]       Comprime imagem -> .PP")
    print("    pp d <arquivo.PP> [-o SAIDA]    Descomprime .PP -> imagem")
    print("    pp i <arquivo.PP>               Mostra info do .PP")
    print("    pp engine                       Status do motor")
    print("    pp help                         Mostra esta ajuda")
    print("    pp version                      Versao")
    print()
    print("  MODOS DE COMPRESSAO:")
    print()
    print("    pp c foto.jpg            Lossy (padrao, qualidade 75)")
    print("    pp c foto.jpg -q 90      Lossy, qualidade 90")
    print("    pp c foto.png -l         LOSSLESS - sem perda de pixels")
    print()
    print("  EXEMPLOS:")
    print()
    print("    pp c foto.jpg                   foto.jpg -> foto.PP (lossy)")
    print("    pp c foto.png -l                foto.png -> foto.PP (lossless)")
    print("    pp c foto.bmp -q 50 -o out.PP   Saida customizada")
    print("    pp d foto.PP                    -> foto_restored.png")
    print("    pp d foto.PP -o saida.jpg       Saida JPG")
    print("    pp i foto.PP                    Ver metadados + modo")
    print()
    print("  FORMATOS SUPORTADOS (entrada):")
    print()
    print("    PNG, JPEG, BMP, TIFF, GIF, WEBP, ICO, TGA, PPM, PGM,")
    print("    PCX, PSD, DDS, APNG, JP2, e muitos outros (via Pillow)")
    print()
    print("  QUALIDADE (modo lossy):")
    print()
    print("     1-30  = Maxima compressao (qualidade mais baixa)")
    print("    31-60  = Balanceado")
    print("    61-80  = Alta qualidade (padrao: 75)")
    print("    81-100 = Quase sem perdas")
    print()
    print("  FLAG -l / --lossless:")
    print()
    print("    Ativa compressao SEM PERDAS usando Middle-Out DPCM + RCT.")
    print("    Garante reconstrucao pixel-perfeita, verificada por SHA-256.")
    print("    Arquivo comprimido maior que o modo lossy, mas sem degradacao.")
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


def _parse_lossless(args: list) -> bool:
    """Retorna True se -l/--lossless estiver nos args."""
    return any(a in ('-l', '--lossless') for a in args)


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
        print("  Uso: pp c <imagem> [-q QUALIDADE] [-l] [-o SAIDA]")
        return 1

    input_path = positional[0]
    quality    = _parse_quality(args)
    lossless   = _parse_lossless(args)
    output_path = _parse_output(args)

    if not os.path.exists(input_path):
        print(f"  ERRO: Arquivo nao encontrado: {input_path}")
        return 1

    if not lossless and not 1 <= quality <= 100:
        print(f"  ERRO: Qualidade deve estar entre 1 e 100 (recebido: {quality})")
        return 1

    print(BANNER)
    print(f"  Comprimindo:  {input_path}")
    if lossless:
        print(f"  Modo:         LOSSLESS (sem perdas) - Middle-Out DPCM + RCT")
    else:
        print(f"  Qualidade:    {quality}/100")
        print(f"  Modo:         LOSSY - DCT + Quantizacao adaptativa Middle-Out")
    print("  Processando...")

    try:
        stats = compress(input_path, output_path, quality, lossless=lossless)
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


def cmd_verify(args: list) -> int:
    """Verifica integridade: comprime lossless, descomprime, compara SHA-256."""
    positional = _get_positional(args)
    if not positional:
        print("  ERRO: Informe a imagem para verificar.")
        print("  Uso: pp verify <imagem>")
        return 1

    import tempfile
    input_path = positional[0]
    if not os.path.exists(input_path):
        print(f"  ERRO: Arquivo nao encontrado: {input_path}")
        return 1

    print(BANNER)
    print(f"  Verificando integridade de: {input_path}")
    print("  Comprimindo (lossless) e descomprimindo para comparacao...")
    print()

    try:
        with tempfile.TemporaryDirectory() as tmp:
            pp_path  = os.path.join(tmp, 'test.PP')
            out_path = os.path.join(tmp, 'test_restored.png')

            c_stats = compress(input_path, pp_path, lossless=True)
            d_stats = decompress(pp_path, out_path)

            v = d_stats.get('integrity_verified')
            W = 66
            print("=" * W)
            print("         PIED PIPER - VERIFICACAO DE INTEGRIDADE")
            print("=" * W)
            print(f"  Arquivo:        {input_path}")
            print(f"  Hash original:  {d_stats.get('original_hash', 'N/A')[:32]}...")
            print(f"  Hash restaurado:{d_stats.get('restored_hash',  'N/A')[:32]}...")
            print(f"  Compressao .PP: {_human(c_stats['compressed_size'])} "
                  f"(ratio {c_stats['compression_ratio']}:1)")
            print("-" * W)
            if v is True:
                print("  RESULTADO: APROVADO - reconstrucao pixel-perfeita garantida")
                print("  O algoritmo Middle-Out DPCM e VERDADEIRAMENTE LOSSLESS.")
            elif v is False:
                print("  RESULTADO: FALHOU - dados corrompidos na compressao!")
            else:
                print("  RESULTADO: Nao foi possivel verificar (hash ausente)")
            print("=" * W)
            print()
            return 0 if v is not False else 1
    except Exception as e:
        print(f"\n  ERRO: {e}")
        import traceback
        traceback.print_exc()
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
    'verify': cmd_verify,    'check': cmd_verify,
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
