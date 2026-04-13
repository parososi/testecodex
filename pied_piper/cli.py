"""
Pied Piper CLI - Interface de linha de comando.

Compressor universal para QUALQUER tipo de arquivo.

Comandos:
    pp c <arquivo|pasta> [-q 75] [-l]  Comprimir qualquer arquivo ou pasta para .PP
    pp d <arquivo.PP> [-o SAIDA]       Descomprimir .PP para arquivo original
    pp i <arquivo.PP>                  Mostrar informacoes do .PP
    pp verify <arquivo>                Verificar integridade (qualquer arquivo)
    pp q <original> <restaurado>       Comparar qualidade (imagens)
    pp bench <arquivo>                 Benchmark de todos os algoritmos
    pp list <arquivo.PP>               Listar arquivos em bundle
    pp stats <arquivo>                 Estatisticas do arquivo sem comprimir
    pp engine                          Status do motor de compressao
    pp help                            Mostrar ajuda
"""

import os
import sys
import time
import hashlib
import threading

from pied_piper import __version__
from pied_piper.codec import (
    compress, decompress, info, engine_info, PP_EXTENSION,
    compress_folder, decompress_bundle, is_bundle, quality_check,
    compress_file, decompress_file, is_universal,
    smart_compress, smart_decompress,
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
        '\u2714\u2716\u280b\u2588\u2591\u2502\u250c\u2510\u2514\u2518'.encode(enc)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


_UNICODE = _COLOR and _has_unicode()

# Caracteres unicode usados em barras/linhas
_BLOCK_FULL  = '\u2588'   # █
_BLOCK_MED   = '\u2593'   # ▓
_BLOCK_LIGHT = '\u2591'   # ░
_HLINE_THIN  = '\u2500'   # ─
_HLINE_THICK = '\u2550'   # ═
_VLINE       = '\u2502'   # │
_CORNER_TL   = '\u256d'   # ╭
_CORNER_TR   = '\u256e'   # ╮
_CORNER_BL   = '\u2570'   # ╰
_CORNER_BR   = '\u256f'   # ╯
_ARROW_R     = '\u25b6'   # ▶
_DIAMOND     = '\u25c6'   # ◆
_STAR        = '\u2605'   # ★
_CIRCLE      = '\u25cf'   # ●
_SPARK       = '\u2737'   # ✷


def _c(code):
    return code if _COLOR else ''


RESET   = _c('\033[0m')
BOLD    = _c('\033[1m')
DIM     = _c('\033[2m')
ITALIC  = _c('\033[3m')
UNDER   = _c('\033[4m')
CYAN    = _c('\033[96m')
GREEN   = _c('\033[92m')
YELLOW  = _c('\033[93m')
RED     = _c('\033[91m')
BLUE    = _c('\033[94m')
MAGENTA = _c('\033[95m')
WHITE   = _c('\033[97m')
GRAY    = _c('\033[90m')

# Cores extras para gradientes
C_ORANGE  = _c('\033[38;5;208m')
C_PINK    = _c('\033[38;5;213m')
C_LIME    = _c('\033[38;5;118m')
C_SKY     = _c('\033[38;5;117m')
C_VIOLET  = _c('\033[38;5;141m')
C_GOLD    = _c('\033[38;5;220m')
C_TEAL    = _c('\033[38;5;43m')
C_CORAL   = _c('\033[38;5;210m')

# Backgrounds
BG_GREEN  = _c('\033[42m')
BG_RED    = _c('\033[41m')
BG_BLUE   = _c('\033[44m')
BG_YELLOW = _c('\033[43m')
BG_CYAN   = _c('\033[46m')
BG_GRAY   = _c('\033[48;5;236m')

OK   = (f'{GREEN}\u2714{RESET}' if _UNICODE else f'{GREEN}+{RESET}')
FAIL = (f'{RED}\u2716{RESET}'   if _UNICODE else f'{RED}x{RESET}')
WARN = (f'{YELLOW}\u26a0{RESET}' if _UNICODE else f'{YELLOW}!{RESET}')
INFO = (f'{CYAN}\u25cf{RESET}'  if _UNICODE else f'{CYAN}*{RESET}')


# ---------------------------------------------------------------------------
# Spinner animado com gradiente de cores
# ---------------------------------------------------------------------------

class Spinner:
    _FRAMES_UNI   = ['\u280b', '\u2819', '\u2839', '\u2838',
                     '\u283c', '\u2834', '\u2826', '\u2827',
                     '\u2807', '\u280f']
    _FRAMES_ASCII = ['|', '/', '-', '\\']
    _COLORS = [CYAN, C_SKY, BLUE, C_VIOLET, MAGENTA, C_PINK,
               C_CORAL, C_ORANGE, C_GOLD, YELLOW, C_LIME, GREEN, C_TEAL]

    def __init__(self, msg: str):
        self.msg = msg
        self._stop = threading.Event()
        self._thread = None
        self._frames = self._FRAMES_UNI if _UNICODE else self._FRAMES_ASCII

    def _run(self):
        i = 0
        while not self._stop.is_set():
            f = self._frames[i % len(self._frames)]
            color = self._COLORS[i % len(self._COLORS)]
            sys.stdout.write(f'\r  {color}{BOLD}{f}{RESET} {WHITE}{self.msg}{RESET} ')
            sys.stdout.flush()
            time.sleep(0.07)
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
        # Gradient bar: green -> cyan -> blue
        bar_chars = ''
        for i in range(width):
            if i < filled:
                if i < width // 3:
                    bar_chars += f'{GREEN}{_BLOCK_FULL}'
                elif i < 2 * width // 3:
                    bar_chars += f'{C_TEAL}{_BLOCK_FULL}'
                else:
                    bar_chars += f'{CYAN}{_BLOCK_FULL}'
            else:
                bar_chars += f'{GRAY}{_BLOCK_LIGHT}'
        inner = f'{bar_chars}{RESET}'
    else:
        inner = f'{GREEN}{"#" * filled}{DIM}{"." * (width - filled)}{RESET}'
    return f'[{inner}]'


def _mode_badge(lossless: bool) -> str:
    if lossless:
        if _UNICODE:
            return f'{GREEN}{BOLD}{_DIAMOND} SEM PERDAS {_DIAMOND}{RESET}'
        return f'{GREEN}{BOLD}[ SEM PERDAS ]{RESET}'
    if _UNICODE:
        return f'{YELLOW}{BOLD}{_DIAMOND} LOSSY {_DIAMOND}{RESET}'
    return f'{YELLOW}{BOLD}[   LOSSY    ]{RESET}'


def _hline(W: int = 64) -> None:
    if _UNICODE:
        print(f'  {DIM}{_HLINE_THIN * W}{RESET}')
    else:
        print('  ' + '-' * W)


def _dline(W: int = 64) -> None:
    if _UNICODE:
        print(f'  {C_TEAL}{_HLINE_THICK * W}{RESET}')
    else:
        print('  ' + '=' * W)


def _boxline(W: int = 64, style: str = 'top') -> None:
    """Draw a rounded box border."""
    if not _UNICODE:
        _hline(W)
        return
    if style == 'top':
        print(f'  {C_SKY}{_CORNER_TL}{_HLINE_THIN * W}{_CORNER_TR}{RESET}')
    elif style == 'bottom':
        print(f'  {C_SKY}{_CORNER_BL}{_HLINE_THIN * W}{_CORNER_BR}{RESET}')
    elif style == 'mid':
        print(f'  {C_SKY}{_VLINE}{DIM}{_HLINE_THIN * W}{RESET}{C_SKY}{_VLINE}{RESET}')


def _header(title: str, W: int = 64) -> None:
    print()
    if _UNICODE:
        _boxline(W, 'top')
        pad = W - len(title.replace('\033[0m', '').replace('\033[1m', '')
                         .replace('\033[92m', '').replace('\033[93m', '')
                         .replace('\033[91m', '').replace('\033[96m', '')
                         .replace('\033[95m', '').replace('\033[97m', '')
                         .replace('\033[94m', '').replace('\033[90m', '')
                         .replace('\033[2m', '').replace('\033[3m', '')
                         .replace('\033[4m', ''))
        # just center the title roughly
        print(f'  {C_SKY}{_VLINE}{RESET} {BOLD}{WHITE}{title}{RESET}')
        _boxline(W, 'bottom')
    else:
        _dline(W)
        print(f'  {BOLD}{WHITE}{title}{RESET}')
        _dline(W)


def _section(title: str) -> None:
    """Colorful section divider."""
    if _UNICODE:
        print(f'  {C_ORANGE}{_ARROW_R}{RESET} {BOLD}{C_GOLD}{title}{RESET}')
    else:
        print(f'  > {BOLD}{YELLOW}{title}{RESET}')
    _hline()


def _row(label: str, value: str) -> None:
    if _UNICODE:
        print(f'  {C_SKY}{_VLINE}{RESET} {CYAN}{label:<22}{RESET}{value}')
    else:
        print(f'  {CYAN}{label:<24}{RESET}{value}')


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

def _print_banner() -> None:
    # Gradient colors for the ASCII art
    _GRAD = [C_TEAL, CYAN, C_SKY, BLUE, C_VIOLET, MAGENTA]

    art = [
        r"   ____  _          _   ____  _              ",
        r"  |  _ \(_) ___  __| | |  _ \(_)_ __   ___ _ __",
        r"  | |_) | |/ _ \/ _` | | |_) | | '_ \ / _ \ '__|",
        r"  |  __/| |  __/ (_| | |  __/| | |_) |  __/ |  ",
        r"  |_|   |_|\___|\__,_| |_|   |_| .__/ \___|_|  ",
        r"                               |_|              ",
    ]
    print()
    for i, line in enumerate(art):
        color = _GRAD[i % len(_GRAD)]
        print(f'{color}{BOLD}{line}{RESET}')

    if _UNICODE:
        tag = f'{C_GOLD}{_STAR}{RESET}'
        print(f'  {tag} {C_SKY}Middle-Out Compression Engine{RESET}  '
              f'{DIM}{_HLINE_THIN * 3}{RESET}  '
              f'{C_VIOLET}v{__version__}{RESET}  '
              f'{DIM}{_HLINE_THIN * 3}{RESET}  '
              f'{tag}')
    else:
        print(f'  {DIM}Middle-Out Compression Engine  {GRAY}v{__version__}{RESET}')
    print()


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
    _row('Formato original:', f'{C_ORANGE}{s["original_format"]}{RESET} ({s["original_mode"]})')
    _hline()
    _section('DIMENSOES')
    _row('Dimensoes:', f'{WHITE}{s["width"]} x {s["height"]}{RESET} pixels')
    _row('Total de pixels:', f'{s["total_pixels"]:,}')
    _row('Megapixels:', f'{C_GOLD}{s["megapixels"]} MP{RESET}')
    _row('Canal Alpha:', f'{GREEN}Sim{RESET}' if s['has_alpha'] else f'{GRAY}Nao{RESET}')
    _hline()
    _section('RESULTADO DA COMPRESSAO')
    _row('Tamanho original:', f'{WHITE}{_human(s["original_size"])}{RESET}')
    _row('Tamanho comprimido:', f'{C_LIME}{BOLD}{_human(s["compressed_size"])}{RESET}')
    _row('Taxa de compressao:', f'{GREEN}{BOLD}{s["compression_ratio"]}:1{RESET}')
    _row('Bits por pixel:', f'{C_SKY}{s["bits_per_pixel"]}{RESET}')
    r = s['reduction_percent']
    if r >= 0:
        _row('Reducao:', f'{GREEN}{BOLD}{r}%{RESET}')
        print(f'  {"":24}{_bar(r)}  {GREEN}{r}%{RESET}')
    else:
        _row('Reducao:', f'{RED}{BOLD}{r}% (arquivo cresceu){RESET}')
    _hline()
    _section('ALGORITMO MIDDLE-OUT')
    if lossless:
        strategy_label = s.get('lossless_strategy_label', 'Pixel-perfeito')
        _row('Modo:', f'{GREEN}{BOLD}LOSSLESS{RESET} {C_TEAL}\u2013 {strategy_label}{RESET}')
        _row('PSNR:', f'{GREEN}{s["psnr_str"]}{RESET}')
    else:
        _row('Modo:', f'{YELLOW}{BOLD}LOSSY{RESET} {C_ORANGE}\u2013 DCT + Quantizacao adaptativa{RESET}')
        _row('Qualidade:', f'{C_GOLD}{BOLD}{s["quality"]}/100{RESET}')
        _row('PSNR:', f'{C_SKY}{s["psnr_str"]}{RESET}')
    if s["total_blocks"] > 0:
        _row('Blocos processados:', f'{WHITE}{s["total_blocks"]:,}{RESET}')
        _row('Blocos preditos:', f'{C_VIOLET}{s["predicted_blocks"]:,}{RESET} ({s["prediction_percent"]}%)')
        if not lossless:
            _row('Blocos vazios:', f'{C_SKY}{s["zero_blocks"]:,}{RESET} ({s["zero_blocks_percent"]}%)')
        _row('Esparsidade:', f'{C_TEAL}{s["coefficient_sparsity"]}%{RESET}')
    _hline()
    _row('Tempo:', f'{C_GOLD}{s["time_seconds"]}s{RESET}')
    _row('Throughput:', f'{C_LIME}{s["pixels_per_second"]:,} px/s{RESET}')
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
    _row('Formato original:', f'{C_ORANGE}{s["original_format"]}{RESET}')
    _hline()
    _section('DIMENSOES')
    _row('Dimensoes:', f'{WHITE}{s["width"]} x {s["height"]}{RESET} pixels')
    _row('Total de pixels:', f'{s["total_pixels"]:,}')
    _row('Megapixels:', f'{C_GOLD}{s["megapixels"]} MP{RESET}')
    _row('Canal Alpha:', f'{GREEN}Sim{RESET}' if s['has_alpha'] else f'{GRAY}Nao{RESET}')
    _hline()
    _section('RESULTADO')
    _row('Tamanho .PP:', f'{WHITE}{_human(s["pp_size"])}{RESET}')
    _row('Tamanho restaurado:', f'{C_LIME}{BOLD}{_human(s["restored_size"])}{RESET}')
    if lossless:
        strat = s.get('lossless_strategy', '')
        strat_labels = {
            'stored': 'Bytes originais (sem re-codificacao)',
            'png':    'PNG pixel-perfeito (deflate otimizado)',
            'dpcm':   'RCT + DPCM espiral + zlib',
        }
        if strat:
            _row('Estrategia:', f'{C_VIOLET}{strat_labels.get(strat, strat)}{RESET}')
        _row('PSNR:', f'{GREEN}{s["psnr_str"]}{RESET}')
        v = s.get('integrity_verified')
        if v is True:
            check = f'{GREEN}{BOLD}\u2714 VERIFICADA \u2013 pixels identicos{RESET}' if _UNICODE else f'{GREEN}OK \u2013 pixels identicos{RESET}'
            _row('Integridade SHA-256:', check)
        elif v is False:
            _row('Integridade SHA-256:', f'{RED}{BOLD}\u2716 FALHOU \u2013 dados corrompidos!{RESET}')
        else:
            _row('Integridade SHA-256:', f'{YELLOW}hash original nao disponivel{RESET}')
    else:
        _row('Qualidade usada:', f'{C_GOLD}{BOLD}{s["quality"]}/100{RESET}')
        _row('PSNR:', f'{C_SKY}{s["psnr_str"]}{RESET}')
    _hline()
    _row('Tempo:', f'{C_GOLD}{s["time_seconds"]}s{RESET}')
    _row('Throughput:', f'{C_LIME}{s["pixels_per_second"]:,} px/s{RESET}')
    _dline()
    print(f'  {OK} {GREEN}{BOLD}Concluido com sucesso!{RESET}')
    print()


def _print_compress_universal_stats(s: dict) -> None:
    _header(f'PIED PIPER \u2014 COMPRESSAO UNIVERSAL    {_mode_badge(True)}')
    print()
    _row('Entrada:', f'{WHITE}{s["input_file"]}{RESET}')
    _row('Saida:', f'{WHITE}{s["output_file"]}{RESET}')
    _row('Tipo:', f'{C_ORANGE}{BOLD}{s.get("original_ext", "N/A")}{RESET}')
    _hline()
    _section('RESULTADO DA COMPRESSAO')
    _row('Tamanho original:', f'{WHITE}{_human(s["original_size"])}{RESET}')
    _row('Tamanho comprimido:', f'{C_LIME}{BOLD}{_human(s["compressed_size"])}{RESET}')
    diff = s['original_size'] - s['compressed_size']
    if diff >= 0:
        _row('Economia:', f'{GREEN}{BOLD}{_human(diff)}{RESET}')
    else:
        _row('Overhead:', f'{RED}{_human(-diff)}{RESET}')
    ratio = s['compression_ratio']
    _row('Taxa de compressao:', f'{GREEN}{BOLD}{ratio}:1{RESET}')
    r = s['reduction_percent']
    if r >= 0:
        _row('Reducao:', f'{GREEN}{BOLD}{r}%{RESET}')
        print(f'  {"":24}{_bar(r)}  {GREEN}{r}%{RESET}')
    else:
        _row('Reducao:', f'{RED}{BOLD}{r}% (arquivo cresceu){RESET}')
    _hline()
    _section('ALGORITMO SELECIONADO')
    _row('Algoritmo:', f'{C_VIOLET}{BOLD}{s.get("strategy", "N/A")}{RESET}')
    all_results = s.get('all_results', {})
    if all_results:
        _section('COMPARACAO DE ALGORITMOS')
        for alg, size in sorted(all_results.items(), key=lambda x: x[1]):
            if alg == s.get('strategy'):
                marker = f' {C_LIME}{BOLD}{_STAR} melhor{RESET}'
            else:
                marker = ''
            pct = (1 - size / s['original_size']) * 100 if s['original_size'] > 0 else 0
            _row(f'  {alg}:', f'{_human(size)} ({C_TEAL}{pct:.1f}%{RESET} reducao){marker}')
    _hline()
    _row('SHA-256:', f'{GRAY}{s.get("hash", "N/A")[:32]}...{RESET}')
    _row('Modo:', f'{GREEN}{BOLD}LOSSLESS (sem perdas){RESET}')
    _row('Tempo:', f'{C_GOLD}{s["time_seconds"]}s{RESET}')
    _row('Throughput:', f'{C_LIME}{s.get("bytes_per_second", 0):,} bytes/s{RESET}')
    _dline()
    print(f'  {OK} {GREEN}{BOLD}Concluido com sucesso!{RESET}')
    print()


def _print_decompress_universal_stats(s: dict) -> None:
    _header(f'PIED PIPER \u2014 DESCOMPRESSAO UNIVERSAL    {_mode_badge(True)}')
    print()
    _row('Entrada:', f'{WHITE}{s["input_file"]}{RESET}')
    _row('Saida:', f'{WHITE}{s["output_file"]}{RESET}')
    _row('Arquivo original:', f'{C_ORANGE}{s.get("filename", "N/A")}{RESET}')
    _hline()
    _section('RESULTADO')
    _row('Tamanho .PP:', f'{WHITE}{_human(s["pp_size"])}{RESET}')
    _row('Tamanho restaurado:', f'{C_LIME}{BOLD}{_human(s["restored_size"])}{RESET}')
    if s['restored_size'] > 0 and s['pp_size'] > 0:
        ratio = s['restored_size'] / s['pp_size']
        _row('Taxa de expansao:', f'{C_GOLD}{ratio:.2f}:1{RESET}')
    _row('Algoritmo usado:', f'{C_VIOLET}{BOLD}{s.get("strategy", "N/A")}{RESET}')
    _hline()
    v = s.get('integrity_verified')
    if v is True:
        check = f'{GREEN}{BOLD}\u2714 VERIFICADA \u2013 bytes identicos{RESET}' if _UNICODE else f'{GREEN}OK \u2013 bytes identicos{RESET}'
        _row('Integridade SHA-256:', check)
    elif v is False:
        _row('Integridade SHA-256:', f'{RED}{BOLD}\u2716 FALHOU \u2013 dados corrompidos!{RESET}')
    _row('Tempo:', f'{C_GOLD}{s["time_seconds"]}s{RESET}')
    _dline()
    print(f'  {OK} {GREEN}{BOLD}Concluido com sucesso!{RESET}')
    print()


def _print_compress_folder_stats(s: dict) -> None:
    _header(f'PIED PIPER \u2014 PASTA COMPRIMIDA')
    print()
    _row('Pasta de entrada:', f'{WHITE}{s["input_folder"]}{RESET}')
    _row('Saida (.PP bundle):', f'{WHITE}{s["output_file"]}{RESET}')
    _row('Modo:', f'{GREEN}LOSSLESS{RESET}' if s['lossless'] else f'{YELLOW}LOSSY (q={s["quality"]}){RESET}')
    _hline()
    total_files = s.get('total_files', s['total_images'])
    _row('Total de arquivos:', f'{GREEN}{BOLD}{total_files}{RESET}')
    _row('Imagens:', f'{GREEN}{s["total_images"]}{RESET}')
    other = s.get('total_other_files', 0)
    if other:
        _row('Outros arquivos:', f'{CYAN}{other}{RESET}')
    if s['skipped_files']:
        _row('Ignorados:', f'{YELLOW}{len(s["skipped_files"])}{RESET}')
    _hline()
    _row('Tamanho original total:', _human(s['total_original_size']))
    _row('Tamanho bundle .PP:', _human(s['total_compressed_size']))
    r = s['reduction_percent']
    _row('Taxa de compressao:', f'{GREEN}{BOLD}{s["compression_ratio"]}:1{RESET}')
    if r >= 0:
        _row('Reducao:', f'{GREEN}{BOLD}{r}%{RESET}')
        print(f'  {"":24}{_bar(r)}  {GREEN}{r}%{RESET}')
    else:
        _row('Reducao:', f'{RED}{r}% (bundle cresceu){RESET}')
    _hline()
    _row('Tempo:', f'{s["time_seconds"]}s')
    _dline()
    print(f'  {OK} {GREEN}{BOLD}Bundle criado com sucesso!{RESET}')
    print()


def _print_decompress_bundle_stats(s: dict) -> None:
    _header('PIED PIPER \u2014 PASTA DESCOMPRIMIDA')
    print()
    _row('Bundle .PP:', f'{WHITE}{s["input_file"]}{RESET}')
    _row('Pasta de saida:', f'{WHITE}{s["output_dir"]}{RESET}')
    _row('Pasta original:', f'{WHITE}{s["source_folder"]}{RESET}')
    _hline()
    ok_count   = s['files_extracted']
    fail_count = s['files_failed']
    _row('Arquivos extraidos:', f'{GREEN}{BOLD}{ok_count}{RESET}')
    if fail_count:
        _row('Falhas:', f'{RED}{fail_count}{RESET}')
    _hline()
    for r in s['results']:
        icon = OK if r['ok'] else FAIL
        if r['ok']:
            print(f'    {icon} {WHITE}{r["name"]}{RESET}  {GRAY}({_human(r["size"])}){RESET}')
        else:
            print(f'    {icon} {RED}{r["name"]}{RESET}  {GRAY}{r.get("error","")}{RESET}')
    _hline()
    _row('Tempo:', f'{s["time_seconds"]}s')
    _dline()
    print(f'  {OK} {GREEN}{BOLD}Extracao concluida!{RESET}')
    print()


def _print_info(i: dict) -> None:
    # Arquivo universal
    if i.get('universal', False):
        _header(f'PIED PIPER \u2014 INFO DO ARQUIVO .PP    {GREEN}{BOLD}[ UNIVERSAL ]{RESET}')
        print()
        _row('Arquivo:', f'{WHITE}{i["file"]}{RESET}')
        _row('Tamanho total .PP:', _human(i['file_size']))
        _row('Versao do formato:', str(i['version']))
        _row('Header:', _human(i['header_size']))
        _row('Dados comprimidos:', _human(i['data_size']))
        _hline()
        print(f'  {BOLD}{YELLOW}  DADOS DO ARQUIVO ORIGINAL{RESET}')
        _hline()
        _row('Arquivo original:', f'{WHITE}{i.get("filename", "N/A")}{RESET}')
        _row('Extensao:', f'{CYAN}{i.get("original_ext", "N/A")}{RESET}')
        orig_size = i.get('original_size', 0)
        _row('Tamanho original:', _human(orig_size))
        _hline()
        print(f'  {BOLD}{YELLOW}  ESTATISTICAS DE COMPRESSAO{RESET}')
        _hline()
        _row('Algoritmo:', f'{CYAN}{i.get("strategy", "N/A")}{RESET}')
        if orig_size > 0 and i['file_size'] > 0:
            ratio = orig_size / i['file_size']
            reduction = (1 - i['file_size'] / orig_size) * 100
            _row('Taxa de compressao:', f'{GREEN}{BOLD}{ratio:.2f}:1{RESET}')
            if reduction >= 0:
                _row('Reducao:', f'{GREEN}{BOLD}{reduction:.2f}%{RESET}')
                print(f'  {"":24}{_bar(reduction)}  {GREEN}{reduction:.2f}%{RESET}')
            else:
                _row('Reducao:', f'{RED}{reduction:.2f}% (arquivo cresceu){RESET}')
            diff = orig_size - i['file_size']
            if diff >= 0:
                _row('Economia:', f'{GREEN}{_human(diff)}{RESET}')
        _row('Modo:', f'{GREEN}LOSSLESS (sem perdas){RESET}')
        _row('SHA-256:', f'{GRAY}{i.get("hash", "N/A")[:32]}...{RESET}')
        _dline()
        print()
        return

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
    _row('Motor:', f'{C_VIOLET}{BOLD}{e["engine"]}{RESET}')
    avail = e['c_engine_available']
    if avail:
        _row('C engine:', f'{GREEN}{BOLD}Ativo{RESET} {C_TEAL}\u2013 performance nativa{RESET}')
    else:
        _row('C engine:', f'{YELLOW}Inativo{RESET} {DIM}(modo Python/NumPy vetorizado){RESET}')
    ll = e.get('lossless_available')
    _row('Modo lossless:', f'{GREEN}{BOLD}Disponivel{RESET}' if ll else f'{RED}Indisponivel{RESET}')
    uni = e.get('universal_available')
    _row('Compressao universal:', f'{GREEN}{BOLD}Disponivel{RESET}' if uni else f'{RED}Indisponivel{RESET}')
    _row('Biblioteca:', f'{GRAY}{e["library_path"]}{RESET}')
    _row('Linguagens:', f'{C_SKY}{e.get("languages", "N/A")}{RESET}')
    _hline()
    algos = e.get('algorithms', [])
    if algos:
        _section('ALGORITMOS DISPONIVEIS')
        algo_colors = [C_LIME, C_TEAL, C_SKY, C_VIOLET, C_PINK, C_GOLD, C_ORANGE]
        for i, alg in enumerate(algos):
            color = algo_colors[i % len(algo_colors)]
            bullet = _DIAMOND if _UNICODE else '*'
            print(f'    {color}{bullet}{RESET} {WHITE}{alg}{RESET}')
    _hline()
    _row('Versao formato .PP:', f'{C_GOLD}v{e.get("format_version", "?")}{RESET}')
    _row('Versao Pied Piper:', f'{C_VIOLET}{BOLD}{__version__}{RESET}')
    _dline()
    print()


def _print_help() -> None:
    _print_banner()

    def help_section(title):
        if _UNICODE:
            print(f'  {C_ORANGE}{_ARROW_R}{RESET} {BOLD}{C_GOLD}{title}{RESET}')
        else:
            print(f'  {BOLD}{CYAN}{title}{RESET}')
        print()

    def cmd_line(usage, desc):
        arrow = f'{C_TEAL}\u2192{RESET}' if _UNICODE else '->'
        print(f'    {GREEN}{BOLD}{usage:<40}{RESET}{DIM}{desc}{RESET}')

    def example(ex, comment=''):
        c = f'  {GRAY}# {comment}{RESET}' if comment else ''
        bullet = f'{C_SKY}{_CIRCLE}{RESET}' if _UNICODE else f'{GRAY}>{RESET}'
        print(f'    {bullet} {WHITE}{ex}{RESET}{c}')

    help_section('COMANDOS PRINCIPAIS')
    cmd_line('pp c <arquivo|pasta> [-q Q] [-l]',         'Comprime QUALQUER arquivo ou pasta \u2192 .PP')
    cmd_line('pp d <arquivo.PP> [-o SAIDA]',             'Descomprime .PP \u2192 arquivo original')
    cmd_line('pp i <arquivo.PP>',                        'Mostra info e estatisticas do .PP')
    cmd_line('pp verify <arquivo>',                      'Verifica integridade (QUALQUER arquivo)')
    cmd_line('pp q <original> <restaurada>',             'Avalia qualidade (imagens)')
    print()

    help_section('COMANDOS DE ANALISE')
    cmd_line('pp bench <arquivo>',                       'Benchmark de todos os algoritmos')
    cmd_line('pp list <arquivo.PP>',                     'Lista arquivos em um bundle .PP')
    cmd_line('pp stats <arquivo>',                       'Estatisticas do arquivo sem comprimir')
    print()

    help_section('OUTROS COMANDOS')
    cmd_line('pp engine',                                'Status do motor de compressao')
    cmd_line('pp register',                              'Registra .PP no Windows')
    cmd_line('pp help',                                  'Esta ajuda')
    cmd_line('pp version',                               'Versao')
    print()

    help_section('EXEMPLOS \u2014 QUALQUER ARQUIVO')
    example('pp c relatorio.pdf',               'comprime PDF \u2192 relatorio.PP')
    example('pp c dados.csv',                   'comprime CSV \u2192 dados.PP')
    example('pp c programa.exe',                'comprime executavel \u2192 programa.PP')
    example('pp c musica.wav',                  'comprime audio WAV \u2192 musica.PP')
    example('pp d relatorio.PP',                'restaura arquivo original identico')
    print()

    help_section('EXEMPLOS \u2014 VERIFICACAO E BENCHMARK')
    example('pp verify foto.png',               'verifica imagem (pixel-perfeito)')
    example('pp verify relatorio.pdf',          'verifica PDF (bytes identicos)')
    example('pp bench dados.csv',               'testa todos os algoritmos')
    example('pp stats programa.exe',            'analisa arquivo sem comprimir')
    print(f'    {DIM}O comando verify comprime, descomprime e compara SHA-256{RESET}')
    print(f'    {DIM}para garantir que o arquivo e restaurado perfeitamente.{RESET}')
    print()

    help_section('EXEMPLOS \u2014 IMAGENS')
    example('pp c foto.jpg',                    'lossy, qualidade 75 (padrao)')
    example('pp c foto.jpg -q 90',              'lossy, qualidade alta')
    example('pp c foto.png -l',                 'lossless sem perdas')
    example('pp c foto.bmp -o out.PP',          'saida customizada')
    example('pp d foto.PP',                     'descomprime \u2192 formato original')
    example('pp q foto.jpg foto_restored.png',  'avalia perda de qualidade')
    print()

    help_section('EXEMPLOS \u2014 PASTA INTEIRA')
    example('pp c /meus-arquivos/',     'comprime TODOS os arquivos da pasta')
    example('pp c /fotos/ -l',          'lossless para imagens')
    example('pp d meus-arquivos.PP',    'extrai todos os arquivos')
    example('pp list meus-arquivos.PP', 'lista arquivos no bundle')
    print()

    help_section('MODOS DE COMPRESSAO')
    print(f'    {YELLOW}{BOLD}LOSSY{RESET}     {DIM}DCT + Quantizacao adaptativa \u2014 maxima reducao{RESET}')
    print(f'    {GREEN}{BOLD}LOSSLESS{RESET}  {DIM}Multi-estrategia sem perdas \u2014 SHA-256 verificado{RESET}')
    print()
    print(f'    {DIM}  Estrategias lossless (escolhe a menor automaticamente):{RESET}')
    strats = [
        ('stored', 'Bytes originais sem re-codificacao'),
        ('png',    'PNG otimizado via DEFLATE'),
        ('dpcm',   'RCT + DPCM espiral + zlib'),
    ]
    for name, desc in strats:
        bullet = f'{C_TEAL}{_DIAMOND}{RESET}' if _UNICODE else '*'
        print(f'    {bullet} {C_SKY}{name:<8}{RESET} {DIM}{desc}{RESET}')
    print()

    help_section('QUALIDADE (modo lossy, flag -q)')
    print(f'    {RED}{BOLD}  1-30{RESET}   {_bar(15, 20)}  {DIM}Maxima compressao{RESET}')
    print(f'    {C_ORANGE}{BOLD} 31-60{RESET}   {_bar(45, 20)}  {DIM}Balanceado{RESET}')
    print(f'    {C_SKY}{BOLD} 61-80{RESET}   {_bar(70, 20)}  {DIM}Alta qualidade{RESET} {C_GOLD}(padrao: 75){RESET}')
    print(f'    {GREEN}{BOLD}81-100{RESET}   {_bar(90, 20)}  {DIM}Quase sem perdas{RESET}')
    print()

    help_section('COMPRESSAO UNIVERSAL')
    print(f'    {GREEN}{BOLD}QUALQUER ARQUIVO{RESET} e comprimido sem perdas usando o melhor')
    print(f'    algoritmo entre: {C_VIOLET}LZMA{RESET}, {C_SKY}BZ2{RESET}, {C_TEAL}DEFLATE{RESET}, '
          f'{C_ORANGE}BWT+MTF{RESET}, {C_PINK}Delta+LZMA{RESET}')
    print(f'    {DIM}Inspirado no 7-Zip e WinRAR. Integridade verificada por SHA-256.{RESET}')
    print()

    help_section('FORMATOS SUPORTADOS')
    fmt_items = [
        ('Imagens', C_LIME,   'PNG, JPEG, BMP, TIFF, GIF, WEBP, ICO, TGA, PSD'),
        ('Texto',   C_SKY,    'TXT, CSV, JSON, XML, HTML, MD, LOG, YAML'),
        ('Codigo',  C_VIOLET, 'PY, JS, TS, C, CPP, JAVA, RS, GO, RB, PHP'),
        ('Docs',    C_GOLD,   'PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX, ODT'),
        ('Audio',   C_PINK,   'WAV, FLAC, MP3, OGG, AAC, AIFF, WMA'),
        ('Video',   C_ORANGE, 'MP4, AVI, MKV, MOV, WEBM, FLV, WMV'),
        ('Outros',  C_TEAL,   'EXE, DLL, SO, BIN, ZIP, TAR, GZ, 7Z, RAR, *'),
    ]
    for name, color, fmts in fmt_items:
        bullet = f'{color}{_CIRCLE}{RESET}' if _UNICODE else f'{color}*{RESET}'
        print(f'    {bullet} {color}{BOLD}{name:<8}{RESET} {DIM}{fmts}{RESET}')
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
        print(f'  {FAIL} Informe a imagem ou pasta a ser comprimida.')
        print(f'  {DIM}Uso: pp c <imagem|pasta> [-q QUALIDADE] [-l] [-o SAIDA]{RESET}')
        return 1

    input_path  = positional[0]
    quality     = _parse_quality(args)
    lossless    = _parse_lossless(args)
    output_path = _parse_output(args)

    if not os.path.exists(input_path):
        print(f'  {FAIL} Caminho nao encontrado: {RED}{input_path}{RESET}')
        return 1

    # --- Compressao de pasta (bundle) ---
    if os.path.isdir(input_path):
        _print_banner()
        print(f'  {CYAN}Pasta:{RESET}     {WHITE}{input_path}{RESET}')
        if lossless:
            print(f'  {CYAN}Modo:{RESET}      {GREEN}LOSSLESS{RESET} \u2013 sem perdas (padrao para pastas)')
        else:
            print(f'  {CYAN}Modo:{RESET}      {YELLOW}LOSSY{RESET} \u2013 DCT + Quantizacao adaptativa')
            print(f'  {CYAN}Qualidade:{RESET} {quality}/100')
        print()
        sp = Spinner('Comprimindo pasta...')
        sp.start()
        try:
            stats = compress_folder(input_path, output_path,
                                    quality=quality, lossless=lossless)
            sp.stop(True, 'Pasta comprimida!')
            _print_compress_folder_stats(stats)
            return 0
        except Exception as e:
            sp.stop(False, 'Erro ao comprimir pasta')
            print(f'\n  {RED}Detalhe: {e}{RESET}')
            import traceback
            traceback.print_exc()
            return 1

    # --- Compressao de arquivo individual ---
    _print_banner()
    print(f'  {CYAN}Arquivo:{RESET}   {WHITE}{input_path}{RESET}')

    # Detecta se e imagem
    from pied_piper.codec import _is_image_path
    is_image = _is_image_path(input_path)
    if is_image:
        try:
            from PIL import Image as _TestImg
            _t = _TestImg.open(input_path)
            _t.verify()
        except Exception:
            is_image = False

    if is_image:
        if not lossless and not 1 <= quality <= 100:
            print(f'  {FAIL} Qualidade deve estar entre 1 e 100 (recebido: {quality})')
            return 1
        if lossless:
            print(f'  {CYAN}Modo:{RESET}      {GREEN}LOSSLESS{RESET} \u2013 multi-estrategia sem perdas')
        else:
            print(f'  {CYAN}Modo:{RESET}      {YELLOW}LOSSY{RESET} \u2013 DCT + Quantizacao adaptativa')
            print(f'  {CYAN}Qualidade:{RESET} {quality}/100')
        print()

        sp = Spinner('Comprimindo imagem...')
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
    else:
        # Arquivo nao-imagem: compressao universal (sempre lossless)
        ext = os.path.splitext(input_path)[1]
        print(f'  {CYAN}Tipo:{RESET}      {WHITE}{ext or "(sem extensao)"}{RESET}')
        print(f'  {CYAN}Modo:{RESET}      {GREEN}UNIVERSAL LOSSLESS{RESET} \u2013 multi-algoritmo (LZMA/BZ2/DEFLATE/BWT)')
        print()

        sp = Spinner('Comprimindo arquivo...')
        sp.start()
        try:
            stats = compress_file(input_path, output_path)
            sp.stop(True, 'Compressao concluida!')
            _print_compress_universal_stats(stats)
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
        print(f'  {DIM}Uso: pp d <arquivo.PP> [-o SAIDA|PASTA]{RESET}')
        return 1

    input_path  = positional[0]
    output_path = _parse_output(args)

    if not os.path.exists(input_path):
        print(f'  {FAIL} Arquivo nao encontrado: {RED}{input_path}{RESET}')
        return 1

    # --- Auto-detecta bundle (pasta comprimida) ---
    if is_bundle(input_path):
        _print_banner()
        print(f'  {CYAN}Bundle:{RESET}   {WHITE}{input_path}{RESET}')
        print(f'  {DIM}(arquivo de pasta comprimida — extraindo arquivos...){RESET}')
        print()
        sp = Spinner('Extraindo pasta...')
        sp.start()
        try:
            stats = decompress_bundle(input_path, output_path)
            sp.stop(True, 'Extracao concluida!')
            _print_decompress_bundle_stats(stats)
            return 0
        except Exception as e:
            sp.stop(False, 'Erro ao extrair bundle')
            print(f'\n  {RED}Detalhe: {e}{RESET}')
            import traceback
            traceback.print_exc()
            return 1

    # --- Arquivo universal (nao-imagem) ---
    if is_universal(input_path):
        _print_banner()
        print(f'  {CYAN}Arquivo:{RESET}  {WHITE}{input_path}{RESET}')
        print(f'  {DIM}(arquivo universal — descomprimindo...){RESET}')
        print()

        sp = Spinner('Descomprimindo arquivo...')
        sp.start()
        try:
            stats = decompress_file(input_path, output_path)
            sp.stop(True, 'Descompressao concluida!')
            _print_decompress_universal_stats(stats)
            return 0
        except Exception as e:
            sp.stop(False, 'Erro durante a descompressao')
            print(f'\n  {RED}Detalhe: {e}{RESET}')
            import traceback
            traceback.print_exc()
            return 1

    # --- Imagem individual ---
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
    """Verifica integridade: comprime lossless, descomprime, compara SHA-256.
    Funciona com QUALQUER tipo de arquivo (imagens, texto, binarios, etc.)."""
    positional = _get_positional(args)
    if not positional:
        print(f'  {FAIL} Informe o arquivo para verificar.')
        print(f'  {DIM}Uso: pp verify <arquivo>{RESET}')
        print(f'  {DIM}Exemplos:{RESET}')
        print(f'  {DIM}  pp verify foto.png        # verifica imagem{RESET}')
        print(f'  {DIM}  pp verify relatorio.pdf    # verifica PDF{RESET}')
        print(f'  {DIM}  pp verify dados.csv        # verifica CSV{RESET}')
        print(f'  {DIM}  pp verify programa.exe      # verifica executavel{RESET}')
        return 1

    import tempfile
    import hashlib
    input_path = positional[0]
    if not os.path.exists(input_path):
        print(f'  {FAIL} Arquivo nao encontrado: {RED}{input_path}{RESET}')
        return 1

    _print_banner()
    original_size = os.path.getsize(input_path)
    ext = os.path.splitext(input_path)[1]
    print(f'  {CYAN}Arquivo:{RESET}   {WHITE}{input_path}{RESET}')
    print(f'  {CYAN}Tipo:{RESET}      {WHITE}{ext or "(sem extensao)"}{RESET}')
    print(f'  {CYAN}Tamanho:{RESET}   {WHITE}{_human(original_size)}{RESET}')
    print()

    # Detecta se e imagem
    from pied_piper.codec import _is_image_path
    is_image = _is_image_path(input_path)
    if is_image:
        try:
            from PIL import Image as _TestImg
            _t = _TestImg.open(input_path)
            _t.verify()
        except Exception:
            is_image = False

    sp = Spinner('Comprimindo e descomprimindo para verificacao...')
    sp.start()

    try:
        with tempfile.TemporaryDirectory() as tmp:
            pp_path = os.path.join(tmp, 'test.PP')

            if is_image:
                # Verificacao de imagem: comprime lossless e verifica pixels
                out_path = os.path.join(tmp, 'test_restored.png')
                c_stats = compress(input_path, pp_path, lossless=True)
                d_stats = decompress(pp_path, out_path)
                v = d_stats.get('integrity_verified')
                compressed_size = c_stats['compressed_size']
                ratio = c_stats['compression_ratio']
                h_orig = d_stats.get('original_hash', 'N/A')
                h_rest = d_stats.get('restored_hash', 'N/A')
                verify_type = 'imagem (pixel-perfeito)'
            else:
                # Verificacao universal: comprime e verifica bytes via SHA-256
                c_stats = compress_file(input_path, pp_path)
                compressed_size = c_stats['compressed_size']
                ratio = c_stats['compression_ratio']

                # Calcula hash do original
                _hash = hashlib.sha256()
                with open(input_path, 'rb') as _f:
                    for _chunk in iter(lambda: _f.read(65536), b''):
                        _hash.update(_chunk)
                h_orig = _hash.hexdigest()

                # Descomprime
                d_stats = decompress_file(pp_path)
                out_path = d_stats['output_file']
                v = d_stats.get('integrity_verified')

                # Verifica hash do restaurado
                _hash2 = hashlib.sha256()
                with open(out_path, 'rb') as _f:
                    for _chunk in iter(lambda: _f.read(65536), b''):
                        _hash2.update(_chunk)
                h_rest = _hash2.hexdigest()

                # Se pipeline nao verificou, faz a comparacao direta
                if v is None:
                    v = (h_orig == h_rest)
                verify_type = 'arquivo (bytes identicos)'

        sp.stop(v is not False, 'Verificacao concluida!')

        _header('PIED PIPER \u2014 VERIFICACAO DE INTEGRIDADE')
        print()
        _row('Arquivo:', f'{WHITE}{input_path}{RESET}')
        _row('Tipo:', f'{WHITE}{ext or "(sem extensao)"}{RESET}')
        _row('Verificacao:', f'{CYAN}{verify_type}{RESET}')
        _hline()
        _row('Tamanho original:', _human(original_size))
        _row('Tamanho comprimido:', _human(compressed_size))
        _row('Taxa de compressao:', f'{GREEN}{BOLD}{ratio}:1{RESET}')
        r = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
        if r >= 0:
            _row('Reducao:', f'{GREEN}{BOLD}{r:.2f}%{RESET}')
            print(f'  {"":24}{_bar(r)}  {GREEN}{r:.2f}%{RESET}')
        else:
            _row('Reducao:', f'{RED}{r:.2f}% (arquivo cresceu){RESET}')
        _hline()
        _row('SHA-256 original:', f'{GRAY}{h_orig[:32]}...{RESET}')
        _row('SHA-256 restaurado:', f'{GRAY}{h_rest[:32]}...{RESET}')
        _hline()
        if v is True:
            if is_image:
                print(f'  {OK} {GREEN}{BOLD}APROVADO{RESET} \u2013 reconstrucao pixel-perfeita garantida')
                print(f'     O algoritmo Middle-Out DPCM e VERDADEIRAMENTE LOSSLESS.')
            else:
                print(f'  {OK} {GREEN}{BOLD}APROVADO{RESET} \u2013 bytes identicos ao original')
                print(f'     Arquivo restaurado e BIT-A-BIT identico ao original.')
        elif v is False:
            print(f'  {FAIL} {RED}{BOLD}FALHOU{RESET} \u2013 dados corrompidos na compressao!')
            print(f'     Os hashes SHA-256 nao coincidem.')
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


def _quality_badge(level: str) -> str:
    badges = {
        'perfect':    f'{GREEN}{BOLD}[ PIXEL-PERFEITO ]{RESET}',
        'excellent':  f'{GREEN}{BOLD}[   EXCELENTE    ]{RESET}',
        'very_good':  f'{CYAN}{BOLD}[   MUITO BOA    ]{RESET}',
        'good':       f'{YELLOW}{BOLD}[      BOA       ]{RESET}',
        'fair':       f'{YELLOW}{BOLD}[    REGULAR     ]{RESET}',
        'poor':       f'{RED}{BOLD}[     RUIM       ]{RESET}',
    }
    return badges.get(level, f'{GRAY}[  DESCONHECIDA  ]{RESET}')


def _psnr_bar(psnr: float, width: int = 30) -> str:
    """Barra de progresso proporcional ao PSNR (0-50 dB range)."""
    if psnr == float('inf'):
        pct = 100.0
    else:
        pct = min(100.0, max(0.0, psnr / 50.0 * 100.0))
    filled = int(pct / 100.0 * width)
    if psnr == float('inf') or psnr >= 40:
        color = GREEN
    elif psnr >= 30:
        color = YELLOW
    else:
        color = RED
    if _UNICODE:
        inner = f'{color}{_BLOCK_FULL * filled}{GRAY}{_BLOCK_LIGHT * (width - filled)}{RESET}'
    else:
        inner = f'{color}{"#" * filled}{DIM}{"." * (width - filled)}{RESET}'
    return f'[{inner}]'


def _print_quality_stats(s: dict) -> None:
    badge = _quality_badge(s['quality_level'])

    _header(f'PIED PIPER \u2014 AVALIACAO DE QUALIDADE    {badge}')
    print()
    _row('Original:', f'{WHITE}{s["original_path"]}{RESET}')
    _row('Restaurada:', f'{WHITE}{s["restored_path"]}{RESET}')
    _hline()
    _row('Formato original:', s['original_format'])
    _row('Formato restaurado:', s['restored_format'])
    _row('Dimensoes:', f'{s["width"]} x {s["height"]} pixels')
    _row('Total de pixels:', f'{s["total_pixels"]:,}')
    _row('Megapixels:', f'{s["megapixels"]} MP')
    _hline()

    # Tamanhos
    orig_h  = _human(s['original_size'])
    rest_h  = _human(s['restored_size'])
    diff_pct = s['size_diff_pct']
    if diff_pct <= -1:
        diff_str = f'{RED}{diff_pct:+.2f}% (arquivo menor \u2014 possivel perda){RESET}'
    elif diff_pct >= 1:
        diff_str = f'{YELLOW}{diff_pct:+.2f}% (arquivo maior){RESET}'
    else:
        diff_str = f'{GREEN}{diff_pct:+.2f}% (tamanho similar){RESET}'

    _row('Tamanho original:', orig_h)
    _row('Tamanho restaurado:', rest_h)
    _row('Variacao de tamanho:', diff_str)
    _hline()

    # Metricas de qualidade
    print(f'  {BOLD}{YELLOW}  METRICAS DE QUALIDADE{RESET}')
    _hline()

    psnr = s['psnr']
    if psnr == float('inf'):
        psnr_color = GREEN
    elif psnr >= 40:
        psnr_color = GREEN
    elif psnr >= 30:
        psnr_color = YELLOW
    else:
        psnr_color = RED

    _row('PSNR geral:', f'{psnr_color}{BOLD}{s["psnr_str"]}{RESET}')
    if psnr != float('inf'):
        print(f'  {"":24}{_psnr_bar(psnr)}  {psnr_color}{s["psnr_str"]}{RESET}')

    # PSNR por canal
    ch_psnr = s['channel_psnr']
    for ch in ['R', 'G', 'B']:
        v = ch_psnr[ch]
        c = GREEN if v == float('inf') or v >= 40 else (YELLOW if v >= 30 else RED)
        v_str = 'inf' if v == float('inf') else f'{v:.2f} dB'
        _row(f'  PSNR canal {ch}:', f'{c}{v_str}{RESET}')

    _hline()
    _row('SSIM:', f'{CYAN}{BOLD}{s["ssim_str"]}{RESET}  {DIM}(1.0 = identico){RESET}')
    _row('MSE:', f'{s["mse"]:.4f}')
    _row('MAE:', f'{s["mae"]:.4f}')
    _row('Diferenca max. pixel:', f'{s["max_diff"]:.0f} niveis')
    _row('Pixels alterados:', f'{s["changed_pixels"]:,} ({s["changed_pct"]}%)')
    _hline()

    # Resultado final
    level = s['quality_level']
    if level == 'perfect':
        print(f'  {OK} {GREEN}{BOLD}RESULTADO: {s["quality_label"]}{RESET}')
        print(f'     Os pixels sao identicos \u2014 nenhuma perda de qualidade.')
    elif level == 'excellent':
        print(f'  {OK} {GREEN}{BOLD}RESULTADO: {s["quality_label"]}{RESET}')
        print(f'     Perda imperceptivel ao olho humano (PSNR >= 40 dB).')
    elif level == 'very_good':
        print(f'  {OK} {CYAN}{BOLD}RESULTADO: {s["quality_label"]}{RESET}')
        print(f'     Diferenca minima, dificilmente visivel (PSNR 35-40 dB).')
    elif level == 'good':
        print(f'  {WARN} {YELLOW}{BOLD}RESULTADO: {s["quality_label"]}{RESET}')
        print(f'     Pequena perda de qualidade, aceitavel para uso geral (PSNR 30-35 dB).')
    elif level == 'fair':
        print(f'  {WARN} {YELLOW}{BOLD}RESULTADO: {s["quality_label"]}{RESET}')
        print(f'     Perda visivelmente noticavel (PSNR 25-30 dB).')
        print(f'     {DIM}Dica: use -q 90 ou -l para melhor qualidade.{RESET}')
    else:
        print(f'  {FAIL} {RED}{BOLD}RESULTADO: {s["quality_label"]}{RESET}')
        print(f'     Degradacao severa de qualidade (PSNR < 25 dB).')
        print(f'     {DIM}Dica: use -l (lossless) para preservar o original.{RESET}')

    # Alerta especifico para JPEG re-comprimido
    if (s['original_format'] in ('JPEG', 'JPG') and
            s['restored_format'] in ('JPEG', 'JPG') and
            s['size_diff_pct'] < -5 and level not in ('perfect', 'excellent')):
        _hline()
        print(f'  {WARN} {YELLOW}AVISO: Dupla compressao JPEG detectada!{RESET}')
        print(f'     O JPEG original foi re-codificado com qualidade menor.')
        print(f'     {DIM}Para preservar o original use: pp c <imagem> -l{RESET}')

    _dline()
    _row('Tempo de analise:', f'{s["time_seconds"]}s')
    print()


def _image_exts():
    return {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif',
            '.webp', '.ico', '.tga', '.ppm', '.pgm', '.pbm', '.jp2',
            '.jpx', '.j2k', '.j2c', '.pcx', '.psd', '.dds'}


def _collect_images(folder: str) -> list:
    """Retorna lista de nomes de arquivo de imagem ordenados na pasta."""
    exts = _image_exts()
    return sorted(
        f for f in os.listdir(folder)
        if os.path.isfile(os.path.join(folder, f))
        and os.path.splitext(f)[1].lower() in exts
    )


def _print_folder_quality_stats(results: list, orig_folder: str,
                                 rest_folder: str) -> None:
    """Exibe tabela de comparacao para multiplas imagens."""
    _header('PIED PIPER \u2014 COMPARACAO DE PASTAS')
    print()
    _row('Originais:', f'{WHITE}{orig_folder}{RESET}')
    _row('Restauradas:', f'{WHITE}{rest_folder}{RESET}')
    _hline()

    ok = [r for r in results if r.get('ok')]
    fail = [r for r in results if not r.get('ok')]

    if ok:
        psnrs = [r['psnr'] for r in ok if r['psnr'] != float('inf')]
        avg_psnr = sum(psnrs) / len(psnrs) if psnrs else float('inf')
        avg_ssim = sum(r['ssim'] for r in ok) / len(ok)
        perfect  = sum(1 for r in ok if r['quality_level'] == 'perfect')

        print(f'  {BOLD}{YELLOW}  RESULTADO POR IMAGEM{RESET}')
        _hline()
        col_w = 30
        print(f'  {BOLD}{"Arquivo":<{col_w}} {"PSNR":>10} {"SSIM":>8} {"Nivel"}{RESET}')
        _hline()
        for r in ok:
            p = r['psnr']
            p_str = 'inf' if p == float('inf') else f'{p:.2f} dB'
            if p == float('inf') or p >= 40:
                pc = GREEN
            elif p >= 30:
                pc = YELLOW
            else:
                pc = RED
            lvl_labels = {
                'perfect': 'Perfeito', 'excellent': 'Excelente',
                'very_good': 'Muito boa', 'good': 'Boa',
                'fair': 'Regular', 'poor': 'Ruim',
            }
            lvl = lvl_labels.get(r['quality_level'], r['quality_level'])
            name = r['name']
            if len(name) > col_w - 1:
                name = name[:col_w - 4] + '...'
            print(f'  {WHITE}{name:<{col_w}}{RESET} {pc}{p_str:>10}{RESET} '
                  f'{CYAN}{r["ssim"]:.4f}{RESET}   {lvl}')
        _hline()

        print(f'  {BOLD}{YELLOW}  RESUMO AGREGADO{RESET}')
        _hline()
        _row('Imagens comparadas:', f'{GREEN}{BOLD}{len(ok)}{RESET}')
        if fail:
            _row('Falhas:', f'{RED}{len(fail)}{RESET}')
        psnr_str = 'inf (identico)' if avg_psnr == float('inf') else f'{avg_psnr:.2f} dB'
        _row('PSNR medio:', f'{GREEN if avg_psnr >= 40 else YELLOW}{BOLD}{psnr_str}{RESET}')
        if avg_psnr != float('inf'):
            print(f'  {"":24}{_psnr_bar(avg_psnr)}')
        _row('SSIM medio:', f'{CYAN}{BOLD}{avg_ssim:.6f}{RESET}')
        _row('Pixel-perfeitas:', f'{GREEN}{perfect}{RESET} de {len(ok)}')

    for r in fail:
        print(f'  {FAIL} {RED}{r["name"]}: {r.get("error", "erro desconhecido")}{RESET}')

    _dline()
    print()


def cmd_quality(args: list) -> int:
    """Avalia qualidade de imagem(ns) restaurada(s) comparando com o original."""
    positional = _get_positional(args)
    if len(positional) < 2:
        print(f'  {FAIL} Informe a imagem original e a restaurada (ou duas pastas).')
        print(f'  {DIM}Uso: pp q <original> <restaurada>{RESET}')
        print(f'  {DIM}     pp q <pasta_original> <pasta_restaurada>{RESET}')
        return 1

    original_path = positional[0]
    restored_path = positional[1]

    for p in (original_path, restored_path):
        if not os.path.exists(p):
            print(f'  {FAIL} Caminho nao encontrado: {RED}{p}{RESET}')
            return 1

    # --- Comparacao de pastas ---
    if os.path.isdir(original_path) and os.path.isdir(restored_path):
        _print_banner()
        print(f'  {CYAN}Originais:{RESET}   {WHITE}{original_path}{RESET}')
        print(f'  {CYAN}Restauradas:{RESET} {WHITE}{restored_path}{RESET}')
        print()

        orig_imgs = _collect_images(original_path)
        rest_imgs = set(_collect_images(restored_path))

        if not orig_imgs:
            print(f'  {FAIL} Nenhuma imagem encontrada em: {RED}{original_path}{RESET}')
            return 1

        results = []
        total = len(orig_imgs)
        for idx, fname in enumerate(orig_imgs, 1):
            # Tenta match exato, depois match por nome-sem-extensao
            base_no_ext = os.path.splitext(fname)[0]
            match = None
            if fname in rest_imgs:
                match = fname
            else:
                for r in rest_imgs:
                    if os.path.splitext(r)[0] == base_no_ext:
                        match = r
                        break
            if match is None:
                results.append({'name': fname, 'ok': False,
                                 'error': 'sem correspondente na pasta restaurada'})
                continue

            sp = Spinner(f'[{idx}/{total}] {fname}')
            sp.start()
            try:
                s = quality_check(
                    os.path.join(original_path, fname),
                    os.path.join(restored_path, match),
                )
                s['name'] = fname
                s['ok'] = True
                results.append(s)
                sp.stop(True, fname)
            except Exception as e:
                sp.stop(False, fname)
                results.append({'name': fname, 'ok': False, 'error': str(e)})

        _print_folder_quality_stats(results, original_path, restored_path)
        return 0 if any(r.get('ok') for r in results) else 1

    # --- Comparacao de arquivo individual ---
    if os.path.isdir(original_path) or os.path.isdir(restored_path):
        print(f'  {FAIL} Ambos os caminhos devem ser arquivos ou ambos pastas.')
        return 1

    _print_banner()
    print(f'  {CYAN}Original:{RESET}   {WHITE}{original_path}{RESET}')
    print(f'  {CYAN}Restaurada:{RESET} {WHITE}{restored_path}{RESET}')
    print()

    sp = Spinner('Calculando metricas de qualidade...')
    sp.start()

    try:
        stats = quality_check(original_path, restored_path)
        sp.stop(True, 'Analise concluida!')
        _print_quality_stats(stats)
        return 0
    except Exception as e:
        sp.stop(False, 'Erro na analise de qualidade')
        print(f'\n  {RED}Detalhe: {e}{RESET}')
        import traceback
        traceback.print_exc()
        return 1


def cmd_register(args: list) -> int:
    """Registra a extensao .PP no Windows como 'Arquivo Pied Piper'."""
    _print_banner()

    if sys.platform != 'win32':
        print(f'  {WARN} {YELLOW}Registro de tipo de arquivo e especifico do Windows.{RESET}')
        print(f'  {DIM}Em Linux/macOS use o gerenciador de arquivos para associar .PP{RESET}')
        print(f'  {DIM}ao comando: python <caminho>/pp d "%f"{RESET}')
        return 0

    try:
        import winreg

        pp_script = os.path.abspath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pp')
        )
        pp_bat = os.path.abspath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pp.bat')
        )
        open_cmd = f'"{pp_bat}" d "%1"'

        # ProgID: PiedPiper.Image.1
        prog_id = 'PiedPiper.Image.1'
        friendly = 'Arquivo Pied Piper'

        hkcu_classes = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r'Software\Classes', 0,
            winreg.KEY_WRITE | winreg.KEY_CREATE_SUB_KEY,
        )

        # HKCU\Software\Classes\.PP -> PiedPiper.Image.1
        with winreg.CreateKeyEx(hkcu_classes, '.PP') as k:
            winreg.SetValueEx(k, '', 0, winreg.REG_SZ, prog_id)
            winreg.SetValueEx(k, 'Content Type', 0, winreg.REG_SZ, 'image/pp')
            winreg.SetValueEx(k, 'PerceivedType', 0, winreg.REG_SZ, 'image')

        # HKCU\Software\Classes\PiedPiper.Image.1
        with winreg.CreateKeyEx(hkcu_classes, prog_id) as pk:
            winreg.SetValueEx(pk, '', 0, winreg.REG_SZ, friendly)

            # DefaultIcon
            with winreg.CreateKeyEx(pk, 'DefaultIcon') as ik:
                winreg.SetValueEx(ik, '', 0, winreg.REG_SZ, f'"{pp_bat}",0')

            # shell\open\command
            with winreg.CreateKeyEx(pk, r'shell\open\command') as ck:
                winreg.SetValueEx(ck, '', 0, winreg.REG_SZ, open_cmd)

            # shell\open (friendly name)
            with winreg.CreateKeyEx(pk, r'shell\open') as sk:
                winreg.SetValueEx(sk, 'FriendlyAppName', 0,
                                   winreg.REG_SZ, 'Pied Piper')

        winreg.CloseKey(hkcu_classes)

        # Notifica o Explorer para recarregar associacoes
        try:
            import ctypes
            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
        except Exception:
            pass

        _header('PIED PIPER \u2014 REGISTRO DE TIPO DE ARQUIVO')
        print()
        _row('Extensao:', f'{GREEN}.PP{RESET}')
        _row('Tipo registrado:', f'{GREEN}{BOLD}{friendly}{RESET}')
        _row('ProgID:', f'{CYAN}{prog_id}{RESET}')
        _row('Comando abrir:', f'{DIM}{open_cmd}{RESET}')
        _hline()
        print(f'  {OK} {GREEN}{BOLD}Registro concluido!{RESET}')
        print(f'  {DIM}Abra o Explorador de Arquivos — arquivos .PP agora mostram{RESET}')
        print(f'  {DIM}"{friendly}" em vez de "Arquivo Fonte Perl".{RESET}')
        _dline()
        print()
        return 0

    except ImportError:
        print(f'  {FAIL} Modulo winreg nao disponivel.')
        return 1
    except OSError as e:
        print(f'  {FAIL} {RED}Erro ao escrever no registro: {e}{RESET}')
        return 1


def cmd_engine(args: list) -> int:
    _print_banner()
    _print_engine()
    return 0


def cmd_version(args: list) -> int:
    if _UNICODE:
        print(f'  {C_TEAL}{_STAR}{RESET} {CYAN}{BOLD}Pied Piper{RESET} {C_VIOLET}v{__version__}{RESET} '
              f'{DIM}\u2014 Middle-Out Compression Engine{RESET}')
    else:
        print(f'{CYAN}{BOLD}Pied Piper{RESET} v{__version__}')
    return 0


def cmd_help(args: list) -> int:
    _print_help()
    return 0


# ---------------------------------------------------------------------------
# Novos comandos: bench, list, stats
# ---------------------------------------------------------------------------

def cmd_bench(args: list) -> int:
    """Benchmark: testa todos os algoritmos de compressao e mostra comparacao."""
    positional = _get_positional(args)
    if not positional:
        print(f'  {FAIL} Informe o arquivo para benchmark.')
        print(f'  {DIM}Uso: pp bench <arquivo>{RESET}')
        return 1

    input_path = positional[0]
    if not os.path.exists(input_path):
        print(f'  {FAIL} Arquivo nao encontrado: {RED}{input_path}{RESET}')
        return 1

    _print_banner()
    original_size = os.path.getsize(input_path)
    ext = os.path.splitext(input_path)[1]
    print(f'  {CYAN}Arquivo:{RESET}   {WHITE}{input_path}{RESET}')
    print(f'  {CYAN}Tipo:{RESET}      {WHITE}{ext or "(sem extensao)"}{RESET}')
    print(f'  {CYAN}Tamanho:{RESET}   {WHITE}{_human(original_size)}{RESET}')
    print()

    # Le dados do arquivo
    with open(input_path, 'rb') as f:
        raw_data = f.read()

    import lzma
    import bz2
    import zlib

    strategies = [
        ('LZMA (7-Zip)',       lambda d: lzma.compress(d, preset=9 | lzma.PRESET_EXTREME)),
        ('BZ2 (bzip2)',        lambda d: bz2.compress(d, compresslevel=9)),
        ('DEFLATE (zlib)',     lambda d: zlib.compress(d, level=9)),
    ]

    # BWT so para arquivos <= 2MB
    if original_size <= 2 * 1024 * 1024:
        try:
            from pied_piper.compressors.bwt import bwt_compress
            strategies.append(('BWT+MTF',
                lambda d: zlib.compress(bwt_compress(d), level=9)))
        except ImportError:
            pass

    try:
        from pied_piper.compressors.delta import delta_compress
        strategies.append(('Delta+LZMA',
            lambda d: lzma.compress(delta_compress(d), preset=9 | lzma.PRESET_EXTREME)))
    except ImportError:
        pass

    results = []
    best_size = original_size
    best_name = 'stored (sem compressao)'

    _header('PIED PIPER \u2014 BENCHMARK DE COMPRESSAO')
    print()
    _section('TESTANDO ALGORITMOS')

    for name, func in strategies:
        sp = Spinner(f'Testando {name}...')
        sp.start()
        try:
            t0 = time.time()
            compressed = func(raw_data)
            elapsed = time.time() - t0
            c_size = len(compressed)
            ratio = original_size / c_size if c_size > 0 else 0
            reduction = (1 - c_size / original_size) * 100 if original_size > 0 else 0
            throughput = int(original_size / elapsed) if elapsed > 0 else 0
            results.append({
                'name': name, 'size': c_size, 'ratio': ratio,
                'reduction': reduction, 'time': elapsed,
                'throughput': throughput, 'ok': True,
            })
            if c_size < best_size:
                best_size = c_size
                best_name = name
            sp.stop(True, f'{name}: {_human(c_size)} ({reduction:.1f}% reducao) em {elapsed:.3f}s')
        except Exception as e:
            sp.stop(False, f'{name}: erro - {e}')
            results.append({'name': name, 'ok': False, 'error': str(e)})

    print()
    _section('RANKING DE ALGORITMOS')

    ok_results = [r for r in results if r.get('ok')]
    ok_results.sort(key=lambda x: x['size'])

    medals = [f'{C_GOLD}{_STAR}{RESET}', f'{WHITE}{_DIAMOND}{RESET}', f'{C_ORANGE}{_CIRCLE}{RESET}']

    for i, r in enumerate(ok_results):
        medal = medals[i] if i < len(medals) else f'{DIM} {RESET}'
        is_best = r['name'] == best_name
        name_fmt = f'{GREEN}{BOLD}{r["name"]}{RESET}' if is_best else f'{WHITE}{r["name"]}{RESET}'
        bar_w = 20
        pct = max(0, min(100, r['reduction']))
        bar_str = _bar(pct, bar_w)
        best_tag = f' {C_LIME}{BOLD}\u2190 MELHOR{RESET}' if is_best else ''
        print(f'    {medal} {name_fmt:<35} {_human(r["size"]):>12}  '
              f'{bar_str} {C_TEAL}{r["reduction"]:.1f}%{RESET}  '
              f'{GRAY}{r["time"]:.3f}s{RESET}{best_tag}')

    # Stored comparison
    print(f'    {GRAY}  {"Stored (sem compressao)":<33} {_human(original_size):>12}  '
          f'{_bar(0, 20)} 0.0%{RESET}')

    _hline()
    economy = original_size - best_size
    _row('Melhor algoritmo:', f'{GREEN}{BOLD}{best_name}{RESET}')
    _row('Tamanho original:', f'{WHITE}{_human(original_size)}{RESET}')
    _row('Melhor comprimido:', f'{C_LIME}{BOLD}{_human(best_size)}{RESET}')
    if economy > 0:
        _row('Economia:', f'{GREEN}{BOLD}{_human(economy)}{RESET} ({(economy/original_size*100):.1f}%)')
    else:
        _row('Resultado:', f'{YELLOW}Nenhum algoritmo reduziu o tamanho{RESET}')
    _dline()
    print()
    return 0


def cmd_list(args: list) -> int:
    """Lista arquivos contidos em um bundle .PP (pasta comprimida)."""
    positional = _get_positional(args)
    if not positional:
        print(f'  {FAIL} Informe o arquivo .PP bundle.')
        print(f'  {DIM}Uso: pp list <arquivo.PP>{RESET}')
        return 1

    input_path = positional[0]
    if not os.path.exists(input_path):
        print(f'  {FAIL} Arquivo nao encontrado: {RED}{input_path}{RESET}')
        return 1

    import json
    import struct
    from pied_piper.codec import PP_MAGIC

    _print_banner()

    try:
        with open(input_path, 'rb') as f:
            magic = f.read(4)
            if magic != PP_MAGIC:
                print(f'  {FAIL} Nao e um arquivo .PP valido.')
                return 1
            f.read(2)  # version
            header_size = struct.unpack('<I', f.read(4))[0]
            header = json.loads(f.read(header_size).decode('utf-8'))

        if not header.get('bundle', False):
            # Arquivo individual - mostra info basica
            if header.get('universal', False):
                print(f'  {INFO} Arquivo universal (nao e bundle)')
                _row('Nome original:', f'{WHITE}{header.get("filename", "N/A")}{RESET}')
                _row('Extensao:', f'{C_ORANGE}{header.get("original_ext", "N/A")}{RESET}')
                _row('Algoritmo:', f'{C_VIOLET}{header.get("strategy", "N/A")}{RESET}')
            else:
                print(f'  {INFO} Arquivo de imagem individual (nao e bundle)')
                _row('Formato:', f'{C_ORANGE}{header.get("original_format", "N/A")}{RESET}')
                _row('Dimensoes:', f'{WHITE}{header.get("width", 0)} x {header.get("height", 0)}{RESET}')
            print(f'  {DIM}Use "pp i {input_path}" para info detalhada.{RESET}')
            return 0

        # Bundle - lista todos os arquivos
        files = header.get('files', [])
        source = header.get('source_folder', 'N/A')
        bundle_size = os.path.getsize(input_path)

        _header(f'PIED PIPER \u2014 CONTEUDO DO BUNDLE')
        print()
        _row('Arquivo:', f'{WHITE}{input_path}{RESET}')
        _row('Pasta original:', f'{C_ORANGE}{source}{RESET}')
        _row('Tamanho bundle:', f'{WHITE}{_human(bundle_size)}{RESET}')
        _row('Total de arquivos:', f'{C_LIME}{BOLD}{len(files)}{RESET}')
        _hline()

        _section('ARQUIVOS')

        total_orig = 0
        col_w = 32
        print(f'  {BOLD}{"#":>4}  {"Arquivo":<{col_w}} {"Original":>10} {"Comprimido":>12} {"Tipo"}{RESET}')
        _hline()

        for i, entry in enumerate(files, 1):
            name = entry.get('name', '?')
            orig_s = entry.get('original_size', 0)
            comp_s = entry.get('compressed_size', 0) or entry.get('size', 0)
            total_orig += orig_s

            if name and len(name) > col_w - 1:
                name = name[:col_w - 4] + '...'

            if entry.get('universal'):
                tipo = f'{C_VIOLET}{entry.get("format", "?")}{RESET}'
            else:
                w = entry.get('width', 0)
                h = entry.get('height', 0)
                tipo = f'{C_SKY}{w}x{h}{RESET}' if w else f'{GRAY}?{RESET}'

            print(f'  {GRAY}{i:>4}{RESET}  {WHITE}{name:<{col_w}}{RESET} '
                  f'{_human(orig_s):>10} {C_TEAL}{_human(comp_s):>12}{RESET} {tipo}')

        _hline()
        ratio = total_orig / bundle_size if bundle_size > 0 else 0
        _row('Tamanho original total:', f'{WHITE}{_human(total_orig)}{RESET}')
        _row('Taxa de compressao:', f'{GREEN}{BOLD}{ratio:.2f}:1{RESET}')
        _dline()
        print()
        return 0

    except Exception as e:
        print(f'  {FAIL} {RED}Erro ao ler bundle: {e}{RESET}')
        return 1


def cmd_stats(args: list) -> int:
    """Mostra estatisticas detalhadas de um arquivo sem comprimir."""
    positional = _get_positional(args)
    if not positional:
        print(f'  {FAIL} Informe o arquivo para analisar.')
        print(f'  {DIM}Uso: pp stats <arquivo>{RESET}')
        return 1

    input_path = positional[0]
    if not os.path.exists(input_path):
        print(f'  {FAIL} Arquivo nao encontrado: {RED}{input_path}{RESET}')
        return 1

    _print_banner()

    file_size = os.path.getsize(input_path)
    ext = os.path.splitext(input_path)[1].lower()
    basename = os.path.basename(input_path)

    # Calcula SHA-256
    h = hashlib.sha256()
    byte_freq = [0] * 256
    total_bytes = 0
    with open(input_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
            for b in chunk:
                byte_freq[b] += 1
            total_bytes += len(chunk)
    sha = h.hexdigest()

    # Calcula entropia de Shannon
    import math
    entropy = 0.0
    if total_bytes > 0:
        for freq in byte_freq:
            if freq > 0:
                p = freq / total_bytes
                entropy -= p * math.log2(p)

    # Calcula compressibilidade estimada (entropia max = 8 bits/byte)
    compressibility = (1 - entropy / 8.0) * 100 if total_bytes > 0 else 0

    # Detecta tipo
    from pied_piper.codec import _is_image_path
    is_image = _is_image_path(input_path)
    if is_image:
        try:
            from PIL import Image as _TestImg
            _t = _TestImg.open(input_path)
            _t.verify()
        except Exception:
            is_image = False

    # Monta timestamp
    mtime = os.path.getmtime(input_path)
    from datetime import datetime
    mod_date = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')

    _header(f'PIED PIPER \u2014 ANALISE DO ARQUIVO')
    print()
    _row('Arquivo:', f'{WHITE}{BOLD}{basename}{RESET}')
    _row('Caminho:', f'{GRAY}{os.path.dirname(os.path.abspath(input_path))}{RESET}')
    _row('Extensao:', f'{C_ORANGE}{BOLD}{ext or "(nenhuma)"}{RESET}')
    _row('Tamanho:', f'{WHITE}{BOLD}{_human(file_size)}{RESET} ({file_size:,} bytes)')
    _row('Modificado:', f'{C_SKY}{mod_date}{RESET}')
    _hline()

    _section('ANALISE DE CONTEUDO')
    _row('SHA-256:', f'{GRAY}{sha[:40]}...{RESET}')
    _row('Entropia:', f'{C_VIOLET}{BOLD}{entropy:.4f}{RESET} bits/byte (max: 8.0)')

    # Barra visual de entropia
    ent_pct = entropy / 8.0 * 100
    print(f'  {"":24}{_bar(ent_pct)}  {C_VIOLET}{entropy:.2f}/8.00{RESET}')

    # Compressibilidade estimada
    if compressibility > 30:
        comp_color = GREEN
        comp_label = 'Alta \u2013 compressao eficiente esperada'
    elif compressibility > 10:
        comp_color = YELLOW
        comp_label = 'Media \u2013 compressao moderada'
    else:
        comp_color = RED
        comp_label = 'Baixa \u2013 dados ja comprimidos ou aleatorios'

    _row('Compressibilidade:', f'{comp_color}{BOLD}{compressibility:.1f}%{RESET} {DIM}({comp_label}){RESET}')

    # Bytes unicos
    unique_bytes = sum(1 for f in byte_freq if f > 0)
    _row('Bytes unicos:', f'{C_TEAL}{unique_bytes}/256{RESET}')

    # Top bytes mais frequentes
    top_bytes = sorted(enumerate(byte_freq), key=lambda x: -x[1])[:5]
    top_str = ', '.join(
        f'{C_SKY}0x{b:02x}{RESET}={C_GOLD}{cnt:,}{RESET}'
        for b, cnt in top_bytes if cnt > 0
    )
    _row('Bytes mais comuns:', top_str)

    _hline()
    _section('TIPO DE ARQUIVO')

    if is_image:
        try:
            from PIL import Image as _Img
            img = _Img.open(input_path)
            _row('Tipo:', f'{C_LIME}{BOLD}Imagem{RESET}')
            _row('Formato:', f'{C_ORANGE}{img.format}{RESET}')
            _row('Dimensoes:', f'{WHITE}{img.width} x {img.height}{RESET} pixels')
            _row('Modo:', f'{C_SKY}{img.mode}{RESET}')
            _row('Total pixels:', f'{WHITE}{img.width * img.height:,}{RESET}')
            mp = round(img.width * img.height / 1_000_000, 3)
            _row('Megapixels:', f'{C_GOLD}{mp} MP{RESET}')
            _row('Bits/pixel fonte:', f'{C_VIOLET}{round(file_size * 8 / (img.width * img.height), 2)}{RESET}')
            img.close()
        except Exception:
            _row('Tipo:', f'{C_LIME}Imagem (erro ao abrir detalhes){RESET}')
    else:
        # Detecta se e texto ou binario
        null_count = byte_freq[0]
        text_chars = sum(byte_freq[i] for i in range(32, 127)) + byte_freq[10] + byte_freq[13] + byte_freq[9]
        text_ratio = text_chars / total_bytes * 100 if total_bytes > 0 else 0

        if text_ratio > 85:
            _row('Tipo:', f'{C_SKY}{BOLD}Texto/Codigo{RESET}')
        elif null_count > total_bytes * 0.01:
            _row('Tipo:', f'{C_ORANGE}{BOLD}Binario{RESET}')
        else:
            _row('Tipo:', f'{C_VIOLET}{BOLD}Misto{RESET}')
        _row('Conteudo texto:', f'{C_TEAL}{text_ratio:.1f}%{RESET}')

    # Recomendacao
    _hline()
    _section('RECOMENDACAO')
    if is_image:
        print(f'    {OK} {WHITE}Use {GREEN}pp c {basename}{RESET} para lossy ou {GREEN}pp c {basename} -l{RESET} para lossless')
    elif compressibility < 5:
        print(f'    {WARN} {YELLOW}Arquivo parece ja estar comprimido. Resultado pode ser marginal.{RESET}')
        print(f'    {DIM}   Tente: pp c {basename}{RESET}')
    else:
        est_savings = file_size * compressibility / 100
        print(f'    {OK} {WHITE}Economia estimada: ~{GREEN}{BOLD}{_human(est_savings)}{RESET}')
        print(f'    {DIM}   Comando: pp c {basename}{RESET}')

    _dline()
    print()
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
    'q': cmd_quality,        'quality': cmd_quality,       'qcheck': cmd_quality,
    'bench': cmd_bench,      'benchmark': cmd_bench,
    'list': cmd_list,        'ls': cmd_list,               'dir': cmd_list,
    'stats': cmd_stats,      'stat': cmd_stats,            'analyze': cmd_stats,
    'register': cmd_register,
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
