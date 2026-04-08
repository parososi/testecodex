"""
Pied Piper CLI - Interface de linha de comando.

Comandos:
    pp c <imagem> [-q 75] [-l]  Comprimir imagem para .PP
    pp d <arquivo.PP>            Descomprimir .PP para PNG
    pp i <arquivo.PP>            Mostrar informacoes do .PP
    pp engine                    Status do motor de compressao
    pp verify <img>              Verificar integridade lossless
    pp help                      Mostrar ajuda
"""

import os
import sys
import time
import threading

from pied_piper import __version__
from pied_piper.codec import (
    compress, decompress, info, engine_info, PP_EXTENSION
)


# ---------------------------------------------------------------------------
# Cores ANSI e suporte Windows
# ---------------------------------------------------------------------------

def _enable_win_ansi():
    if sys.platform == 'win32':
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            handle = k32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            k32.GetConsoleMode(handle, ctypes.byref(mode))
            k32.SetConsoleMode(handle, mode.value | 0x0004)
        except Exception:
            pass


_enable_win_ansi()
_COLOR = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()


def _has_unicode():
    enc = getattr(sys.stdout, 'encoding', None) or 'ascii'
    try:
        '\u2714\u2716\u280b\u2588\u2591'.encode(enc)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


_UNICODE = _COLOR and _has_unicode()


def _c(code):
    return code if _COLOR else ''


RESET   = _c('\033[0m')
BOLD    = _c('\033[1m')
DIM     = _c('\033[2m')
CYAN    = _c('\033[96m')
GREEN   = _c('\033[92m')
YELLOW  = _c('\033[93m')
RED     = _c('\033[91m')
BLUE    = _c('\033[94m')
MAGENTA = _c('\033[95m')
WHITE   = _c('\033[97m')
GRAY    = _c('\033[90m')

OK   = (f'{GREEN}\u2714{RESET}' if _UNICODE else f'{GREEN}+{RESET}')
FAIL = (f'{RED}\u2716{RESET}'   if _UNICODE else f'{RED}x{RESET}')
WARN = (f'{YELLOW}!{RESET}')


# ---------------------------------------------------------------------------
# Spinner animado
# ---------------------------------------------------------------------------

class Spinner:
    _FRAMES_UNI   = ['\u280b', '\u2819', '\u2839', '\u2838',
                     '\u283c', '\u2834', '\u2826', '\u2827',
                     '\u2807', '\u280f']
    _FRAMES_ASCII = ['|', '/', '-', '\\']

    def __init__(self, msg: str):
        self.msg = msg
        self._stop = threading.Event()
        self._thread = None
        self._frames = self._FRAMES_UNI if _UNICODE else self._FRAMES_ASCII

    def _run(self):
        i = 0
        while not self._stop.is_set():
            f = self._frames[i % len(self._frames)]
            sys.stdout.write(f'\r  {CYAN}{f}{RESET} {self.msg} ')
            sys.stdout.flush()
            time.sleep(0.08)
            i += 1
        sys.stdout.write('\r' + ' ' * (len(self.msg) + 10) + '\r')
        sys.stdout.flush()

    def start(self):
        if _COLOR:
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        else:
            print(f'  >> {self.msg}')

    def stop(self, ok: bool = True, msg: str = None):
        if _COLOR:
            self._stop.set()
            if self._thread:
                self._thread.join(timeout=0.5)
        final = msg or self.msg
        icon = OK if ok else FAIL
        print(f'  {icon} {WHITE}{final}{RESET}')


# ---------------------------------------------------------------------------
# Utilitarios de formatacao
# ---------------------------------------------------------------------------

def _human(n: int) -> str:
    for u in ['B', 'KB', 'MB', 'GB', 'TB']:
        if n < 1024:
            return f'{n:.2f} {u}'
        n /= 1024
    return f'{n:.2f} PB'


def _bar(percent: float, width: int = 30) -> str:
    p = max(0.0, min(100.0, percent))
    filled = int(p / 100 * width)
    if _UNICODE:
        inner = f'{GREEN}{"\u2588" * filled}{GRAY}{"\u2591" * (width - filled)}{RESET}'
    else:
        inner = f'{GREEN}{"#" * filled}{DIM}{"." * (width - filled)}{RESET}'
    return f'[{inner}]'


def _mode_badge(lossless: bool) -> str:
    if lossless:
        return f'{GREEN}{BOLD}[ SEM PERDAS ]{RESET}'
    return f'{YELLOW}{BOLD}[   LOSSY    ]{RESET}'


def _hline(W: int = 64) -> None:
    if _UNICODE:
        print(f'  {DIM}{"\u2500" * W}{RESET}')
    else:
        print('  ' + '-' * W)


def _dline(W: int = 64) -> None:
    if _UNICODE:
        print(f'  {CYAN}{"\u2550" * W}{RESET}')
    else:
        print('  ' + '=' * W)


def _header(title: str, W: int = 64) -> None:
    print()
    _dline(W)
    print(f'  {BOLD}{WHITE}{title}{RESET}')
    _dline(W)


def _row(label: str, value: str) -> None:
    print(f'  {CYAN}{label:<24}{RESET}{value}')


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

def _print_banner() -> None:
    art = [
        r"   ____  _          _   ____  _              ",
        r"  |  _ \(_) ___  __| | |  _ \(_)_ __   ___ _ __",
        r"  | |_) | |/ _ \/ _` | | |_) | | '_ \ / _ \ '__|",
        r"  |  __/| |  __/ (_| | |  __/| | |_) |  __/ |  ",
        r"  |_|   |_|\___|\__,_| |_|   |_| .__/ \___|_|  ",
        r"                               |_|              ",
    ]
    print()
    for line in art:
        print(f'{CYAN}{BOLD}{line}{RESET}')
    print(f'  {DIM}Middle-Out Compression Engine  {GRAY}v{__version__}{RESET}')
    print()


# Compatibilidade com codigo legado que acessa BANNER como constante
BANNER = ''


# ---------------------------------------------------------------------------
# Saida de estatisticas
# ---------------------------------------------------------------------------

def _print_compress_stats(s: dict) -> None:
    lossless = s.get('lossless', False)
    badge = _mode_badge(lossless)

    _header(f'PIED PIPER \u2014 COMPRESSAO CONCLUIDA    {badge}')
    print()
    _row('Entrada:', f'{WHITE}{s["input_file"]}{RESET}')
    _row('Saida:', f'{WHITE}{s["output_file"]}{RESET}')
    _row('Formato original:', f'{s["original_format"]} ({s["original_mode"]})')
    _hline()
    _row('Dimensoes:', f'{s["width"]} x {s["height"]} pixels')
    _row('Total de pixels:', f'{s["total_pixels"]:,}')
    _row('Megapixels:', f'{s["megapixels"]} MP')
    _row('Canal Alpha:', 'Sim' if s['has_alpha'] else 'Nao')
    _hline()
    _row('Tamanho original:', _human(s['original_size']))
    _row('Tamanho comprimido:', _human(s['compressed_size']))
    _row('Taxa de compressao:', f'{GREEN}{BOLD}{s["compression_ratio"]}:1{RESET}')
    _row('Bits por pixel:', str(s['bits_per_pixel']))
    r = s['reduction_percent']
    if r >= 0:
        _row('Reducao:', f'{GREEN}{BOLD}{r}%{RESET}')
        print(f'  {"":24}{_bar(r)}  {GREEN}{r}%{RESET}')
    else:
        _row('Reducao:', f'{RED}{r}% (arquivo cresceu){RESET}')
    _hline()
    print(f'  {BOLD}{YELLOW}  ALGORITMO MIDDLE-OUT \u2014 ESTATISTICAS{RESET}')
    _hline()
    if lossless:
        _row('Modo:', f'{GREEN}LOSSLESS \u2013 RCT + DPCM espiral{RESET}')
        _row('Transformada cor:', 'RCT JPEG 2000 reversivel')
        _row('PSNR:', s['psnr_str'])
    else:
        _row('Modo:', f'{YELLOW}LOSSY \u2013 DCT + Quantizacao adaptativa{RESET}')
        _row('Qualidade:', f'{s["quality"]}/100')
        _row('PSNR:', s['psnr_str'])
    _row('Blocos processados:', f'{s["total_blocks"]:,}')
    _row('Blocos preditos:', f'{s["predicted_blocks"]:,} ({s["prediction_percent"]}%)')
    if not lossless:
        _row('Blocos vazios:', f'{s["zero_blocks"]:,} ({s["zero_blocks_percent"]}%)')
    _row('Esparsidade residual:', f'{s["coefficient_sparsity"]}%')
    _hline()
    _row('Tempo:', f'{s["time_seconds"]}s')
    _row('Throughput:', f'{s["pixels_per_second"]:,} px/s')
    _dline()
    print(f'  {OK} {GREEN}{BOLD}Concluido com sucesso!{RESET}')
    print()


def _print_decompress_stats(s: dict) -> None:
    lossless = s.get('lossless', False)
    badge = _mode_badge(lossless)

    _header(f'PIED PIPER \u2014 DESCOMPRESSAO CONCLUIDA    {badge}')
    print()
    _row('Entrada:', f'{WHITE}{s["input_file"]}{RESET}')
    _row('Saida:', f'{WHITE}{s["output_file"]}{RESET}')
    _row('Formato original:', s['original_format'])
    _hline()
    _row('Dimensoes:', f'{s["width"]} x {s["height"]} pixels')
    _row('Total de pixels:', f'{s["total_pixels"]:,}')
    _row('Megapixels:', f'{s["megapixels"]} MP')
    _row('Canal Alpha:', 'Sim' if s['has_alpha'] else 'Nao')
    _hline()
    _row('Tamanho .PP:', _human(s['pp_size']))
    _row('Tamanho restaurado:', _human(s['restored_size']))
    if lossless:
        _row('PSNR:', s['psnr_str'])
        v = s.get('integrity_verified')
        if v is True:
            check = f'{GREEN}\u2714 VERIFICADA \u2013 pixels identicos{RESET}' if _UNICODE else f'{GREEN}OK \u2013 pixels identicos{RESET}'
            _row('Integridade SHA-256:', check)
        elif v is False:
            _row('Integridade SHA-256:', f'{RED}\u2716 FALHOU \u2013 dados corrompidos!{RESET}')
        else:
            _row('Integridade SHA-256:', f'{YELLOW}hash original nao disponivel{RESET}')
    else:
        _row('Qualidade usada:', f'{s["quality"]}/100')
        _row('PSNR:', s['psnr_str'])
    _hline()
    _row('Tempo:', f'{s["time_seconds"]}s')
    _row('Throughput:', f'{s["pixels_per_second"]:,} px/s')
    _dline()
    print(f'  {OK} {GREEN}{BOLD}Concluido com sucesso!{RESET}')
    print()


def _print_info(i: dict) -> None:
    lossless = i.get('lossless', False)
    badge = _mode_badge(lossless)

    _header(f'PIED PIPER \u2014 INFO DO ARQUIVO .PP    {badge}')
    print()
    _row('Arquivo:', f'{WHITE}{i["file"]}{RESET}')
    _row('Tamanho total:', _human(i['file_size']))
    _row('Versao do formato:', str(i['version']))
    _row('Header:', _human(i['header_size']))
    _row('Dados comprimidos:', _human(i['data_size']))
    _hline()
    _row('Dimensoes:', f'{i["width"]} x {i["height"]}')
    _row('Total pixels:', f'{i["total_pixels"]:,}')
    _row('Modo:', f'{GREEN}LOSSLESS (sem perdas){RESET}' if lossless else f'{YELLOW}LOSSY{RESET}')
    _row('Qualidade gravada:', f'{i["quality"]}/100')
    _row('Canal Alpha:', 'Sim' if i['has_alpha'] else 'Nao')
    _row('Formato original:', f'{i["original_format"]} ({i["original_mode"]})')
    _dline()
    print()


def _print_engine() -> None:
    e = engine_info()

    _header('PIED PIPER \u2014 MOTOR DE COMPRESSAO')
    print()
    _row('Motor C:', e['engine'])
    avail = e['c_engine_available']
    _row('C engine disponivel:', f'{GREEN}Sim{RESET}' if avail else f'{YELLOW}Nao (modo Python puro){RESET}')
    ll = e.get('lossless_available')
    _row('Modo lossless:', f'{GREEN}Disponivel{RESET}' if ll else f'{RED}Indisponivel{RESET}')
    _row('Biblioteca:', e['library_path'])
    _row('Linguagens:', e.get('languages', 'N/A'))
    _row('Versao formato .PP:', f'v{e.get("format_version", "?")}')
    _row('Versao Pied Piper:', __version__)
    _dline()
    print()


def _print_help() -> None:
    _print_banner()

    def section(title):
        print(f'  {BOLD}{CYAN}{title}{RESET}')
        print()

    def cmd_line(usage, desc):
        print(f'    {GREEN}{usage:<40}{RESET}{DIM}{desc}{RESET}')

    def example(ex, comment=''):
        c = f'  {GRAY}# {comment}{RESET}' if comment else ''
        print(f'    {GRAY}>{RESET} {WHITE}{ex}{RESET}{c}')

    section('COMANDOS')
    cmd_line('pp c <imagem> [-q Q] [-l]', 'Comprime imagem \u2192 .PP')
    cmd_line('pp d <arquivo.PP> [-o SAIDA]', 'Descomprime .PP \u2192 imagem')
    cmd_line('pp i <arquivo.PP>', 'Mostra info do .PP')
    cmd_line('pp engine', 'Status do motor de compressao')
    cmd_line('pp verify <imagem>', 'Verifica integridade lossless')
    cmd_line('pp help', 'Esta ajuda')
    cmd_line('pp version', 'Versao')
    print()

    section('EXEMPLOS')
    example('pp c foto.jpg', 'lossy, qualidade 75 (padrao)')
    example('pp c foto.jpg -q 90', 'lossy, qualidade alta')
    example('pp c foto.png -l', 'lossless, pixel-perfeito')
    example('pp c foto.bmp -q 50 -o out.PP', 'saida customizada')
    example('pp d foto.PP', 'descomprime \u2192 PNG')
    example('pp d foto.PP -o saida.jpg', 'descomprime \u2192 JPG')
    example('pp i foto.PP', 'ver metadados e modo')
    print()

    section('MODOS DE COMPRESSAO')
    print(f'    {YELLOW}{BOLD}LOSSY{RESET}     DCT + Quantizacao adaptativa \u2014 menor arquivo, qualidade configuravel')
    print(f'    {GREEN}{BOLD}LOSSLESS{RESET}  DPCM + RCT, verificado por SHA-256 \u2014 pixel-perfeito garantido')
    print()

    section('QUALIDADE (modo lossy, flag -q)')
    print(f'    {RED}  1-30{RESET}   {_bar(15, 20)}  Maxima compressao')
    print(f'    {YELLOW} 31-60{RESET}   {_bar(45, 20)}  Balanceado')
    print(f'    {CYAN} 61-80{RESET}   {_bar(70, 20)}  Alta qualidade {DIM}(padrao: 75){RESET}')
    print(f'    {GREEN}81-100{RESET}   {_bar(90, 20)}  Quase sem perdas')
    print()

    section('FORMATOS SUPORTADOS (entrada)')
    print(f'    {DIM}PNG, JPEG, BMP, TIFF, GIF, WEBP, ICO, TGA, PPM, PGM,{RESET}')
    print(f'    {DIM}PCX, PSD, DDS, APNG, JP2, e muitos outros (via Pillow){RESET}')
    print()


# ---------------------------------------------------------------------------
# Parsing de argumentos
# ---------------------------------------------------------------------------

def _parse_quality(args: list) -> int:
    quality = 75
    for i, a in enumerate(args):
        if a in ('-q', '--quality') and i + 1 < len(args):
            try:
                quality = int(args[i + 1])
            except ValueError:
                print(f'  {FAIL} Qualidade invalida: {RED}{args[i + 1]}{RESET}')
                sys.exit(1)
    return quality


def _parse_lossless(args: list) -> bool:
    return any(a in ('-l', '--lossless') for a in args)


def _parse_output(args: list) -> str:
    for i, a in enumerate(args):
        if a in ('-o', '--output') and i + 1 < len(args):
            return args[i + 1]
    return None


def _get_positional(args: list) -> list:
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


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------

def cmd_compress(args: list) -> int:
    positional = _get_positional(args)
    if not positional:
        print(f'  {FAIL} Informe a imagem a ser comprimida.')
        print(f'  {DIM}Uso: pp c <imagem> [-q QUALIDADE] [-l] [-o SAIDA]{RESET}')
        return 1

    input_path  = positional[0]
    quality     = _parse_quality(args)
    lossless    = _parse_lossless(args)
    output_path = _parse_output(args)

    if not os.path.exists(input_path):
        print(f'  {FAIL} Arquivo nao encontrado: {RED}{input_path}{RESET}')
        return 1

    if not lossless and not 1 <= quality <= 100:
        print(f'  {FAIL} Qualidade deve estar entre 1 e 100 (recebido: {quality})')
        return 1

    _print_banner()
    print(f'  {CYAN}Arquivo:{RESET}   {WHITE}{input_path}{RESET}')
    if lossless:
        print(f'  {CYAN}Modo:{RESET}      {GREEN}LOSSLESS{RESET} \u2013 Middle-Out DPCM + RCT')
    else:
        print(f'  {CYAN}Modo:{RESET}      {YELLOW}LOSSY{RESET} \u2013 DCT + Quantizacao adaptativa')
        print(f'  {CYAN}Qualidade:{RESET} {quality}/100')
    print()

    sp = Spinner('Comprimindo...')
    sp.start()

    try:
        stats = compress(input_path, output_path, quality, lossless=lossless)
        sp.stop(True, 'Compressao concluida!')
        _print_compress_stats(stats)
        return 0
    except Exception as e:
        sp.stop(False, 'Erro durante a compressao')
        print(f'\n  {RED}Detalhe: {e}{RESET}')
        import traceback
        traceback.print_exc()
        return 1


def cmd_decompress(args: list) -> int:
    positional = _get_positional(args)
    if not positional:
        print(f'  {FAIL} Informe o arquivo .PP a descomprimir.')
        print(f'  {DIM}Uso: pp d <arquivo.PP> [-o SAIDA]{RESET}')
        return 1

    input_path  = positional[0]
    output_path = _parse_output(args)

    if not os.path.exists(input_path):
        print(f'  {FAIL} Arquivo nao encontrado: {RED}{input_path}{RESET}')
        return 1

    _print_banner()
    print(f'  {CYAN}Arquivo:{RESET}  {WHITE}{input_path}{RESET}')
    print()

    sp = Spinner('Descomprimindo...')
    sp.start()

    try:
        stats = decompress(input_path, output_path)
        sp.stop(True, 'Descompressao concluida!')
        _print_decompress_stats(stats)
        return 0
    except Exception as e:
        sp.stop(False, 'Erro durante a descompressao')
        print(f'\n  {RED}Detalhe: {e}{RESET}')
        import traceback
        traceback.print_exc()
        return 1


def cmd_info(args: list) -> int:
    positional = _get_positional(args)
    if not positional:
        print(f'  {FAIL} Informe o arquivo .PP')
        print(f'  {DIM}Uso: pp i <arquivo.PP>{RESET}')
        return 1

    input_path = positional[0]
    if not os.path.exists(input_path):
        print(f'  {FAIL} Arquivo nao encontrado: {RED}{input_path}{RESET}')
        return 1

    _print_banner()
    try:
        _print_info(info(input_path))
        return 0
    except Exception as e:
        print(f'\n  {FAIL} {RED}{e}{RESET}')
        return 1


def cmd_verify(args: list) -> int:
    """Verifica integridade: comprime lossless, descomprime, compara SHA-256."""
    positional = _get_positional(args)
    if not positional:
        print(f'  {FAIL} Informe a imagem para verificar.')
        print(f'  {DIM}Uso: pp verify <imagem>{RESET}')
        return 1

    import tempfile
    input_path = positional[0]
    if not os.path.exists(input_path):
        print(f'  {FAIL} Arquivo nao encontrado: {RED}{input_path}{RESET}')
        return 1

    _print_banner()
    print(f'  {CYAN}Arquivo:{RESET}  {WHITE}{input_path}{RESET}')
    print()

    sp = Spinner('Comprimindo e descomprimindo para verificacao...')
    sp.start()

    try:
        with tempfile.TemporaryDirectory() as tmp:
            pp_path  = os.path.join(tmp, 'test.PP')
            out_path = os.path.join(tmp, 'test_restored.png')

            c_stats = compress(input_path, pp_path, lossless=True)
            d_stats = decompress(pp_path, out_path)
            v = d_stats.get('integrity_verified')

        sp.stop(v is not False, 'Verificacao concluida!')

        _header('PIED PIPER \u2014 VERIFICACAO DE INTEGRIDADE')
        print()
        _row('Arquivo:', f'{WHITE}{input_path}{RESET}')
        h_orig = d_stats.get('original_hash', 'N/A')
        h_rest = d_stats.get('restored_hash',  'N/A')
        _row('Hash original:', f'{GRAY}{h_orig[:32]}...{RESET}')
        _row('Hash restaurado:', f'{GRAY}{h_rest[:32]}...{RESET}')
        _row('Compressao .PP:', f'{_human(c_stats["compressed_size"])} (ratio {c_stats["compression_ratio"]}:1)')
        _hline()
        if v is True:
            print(f'  {OK} {GREEN}{BOLD}APROVADO{RESET} \u2013 reconstrucao pixel-perfeita garantida')
            print(f'     O algoritmo Middle-Out DPCM e VERDADEIRAMENTE LOSSLESS.')
        elif v is False:
            print(f'  {FAIL} {RED}{BOLD}FALHOU{RESET} \u2013 dados corrompidos na compressao!')
        else:
            print(f'  {WARN} {YELLOW}Nao foi possivel verificar (hash ausente){RESET}')
        _dline()
        print()
        return 0 if v is not False else 1

    except Exception as e:
        sp.stop(False, 'Erro na verificacao')
        print(f'\n  {RED}Detalhe: {e}{RESET}')
        import traceback
        traceback.print_exc()
        return 1


def cmd_engine(args: list) -> int:
    _print_banner()
    _print_engine()
    return 0


def cmd_version(args: list) -> int:
    print(f'{CYAN}{BOLD}Pied Piper{RESET} v{__version__}')
    return 0


def cmd_help(args: list) -> int:
    _print_help()
    return 0


# ---------------------------------------------------------------------------
# Mapa de comandos e entry point
# ---------------------------------------------------------------------------

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
        print(f'  {FAIL} Comando desconhecido: {RED}{cmd}{RESET}')
        print(f'  {DIM}Use "pp help" para ver comandos disponiveis.{RESET}')
        return 1

    return COMMANDS[cmd](args)


if __name__ == '__main__':
    sys.exit(main())
