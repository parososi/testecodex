"""
Pied Piper CLI - Interface de linha de comando.

Compressor universal para QUALQUER tipo de arquivo.

Comandos:
    pp c <arquivo|pasta> [-q 75] [-l]  Comprimir qualquer arquivo ou pasta para .PP
    pp d <arquivo.PP> [-o SAIDA]       Descomprimir .PP para arquivo original
    pp i <arquivo.PP>                  Mostrar informacoes do .PP
    pp verify <arquivo>                Verificar integridade (qualquer arquivo)
    pp q <original> <restaurado>       Comparar qualidade (imagens)
    pp engine                          Status do motor de compressao
    pp help                            Mostrar ajuda

Exemplos rapidos:
    pp c foto.jpg                 Comprime imagem (lossy, qualidade 75)
    pp c foto.png -l              Comprime imagem sem perdas (lossless)
    pp c relatorio.pdf            Comprime PDF (sempre lossless)
    pp c dados.csv                Comprime CSV (sempre lossless)
    pp c musica.wav               Comprime audio WAV (sempre lossless)
    pp c /minha-pasta/            Comprime todos os arquivos da pasta
    pp d foto.PP                  Descomprime qualquer arquivo .PP
    pp verify documento.pdf       Verifica integridade de qualquer arquivo
    pp i arquivo.PP               Mostra estatisticas do arquivo comprimido
"""

import os
import sys
import time
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
        '\u2714\u2716\u280b\u2588\u2591'.encode(enc)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


_UNICODE = _COLOR and _has_unicode()

# Caracteres unicode usados em barras/linhas (evita backslash em f-strings no py3.11)
_BLOCK_FULL  = '\u2588'   # █
_BLOCK_LIGHT = '\u2591'   # ░
_HLINE_THIN  = '\u2500'   # ─
_HLINE_THICK = '\u2550'   # ═


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
        inner = f'{GREEN}{_BLOCK_FULL * filled}{GRAY}{_BLOCK_LIGHT * (width - filled)}{RESET}'
    else:
        inner = f'{GREEN}{"#" * filled}{DIM}{"." * (width - filled)}{RESET}'
    return f'[{inner}]'


def _mode_badge(lossless: bool) -> str:
    if lossless:
        return f'{GREEN}{BOLD}[ SEM PERDAS ]{RESET}'
    return f'{YELLOW}{BOLD}[   LOSSY    ]{RESET}'


def _hline(W: int = 64) -> None:
    if _UNICODE:
        print(f'  {DIM}{_HLINE_THIN * W}{RESET}')
    else:
        print('  ' + '-' * W)


def _dline(W: int = 64) -> None:
    if _UNICODE:
        print(f'  {CYAN}{_HLINE_THICK * W}{RESET}')
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
        strategy_label = s.get('lossless_strategy_label', 'Pixel-perfeito')
        _row('Modo:', f'{GREEN}LOSSLESS \u2013 {strategy_label}{RESET}')
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
        strat = s.get('lossless_strategy', '')
        strat_labels = {
            'stored': 'Bytes originais (sem re-codificacao)',
            'png':    'PNG pixel-perfeito (deflate otimizado)',
            'dpcm':   'RCT + DPCM espiral + zlib',
        }
        if strat:
            _row('Estrategia:', f'{GREEN}{strat_labels.get(strat, strat)}{RESET}')
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


def _print_compress_universal_stats(s: dict) -> None:
    _header(f'PIED PIPER \u2014 COMPRESSAO UNIVERSAL    {GREEN}{BOLD}[ SEM PERDAS ]{RESET}')
    print()
    _row('Entrada:', f'{WHITE}{s["input_file"]}{RESET}')
    _row('Saida:', f'{WHITE}{s["output_file"]}{RESET}')
    _row('Tipo:', f'{CYAN}{s.get("original_ext", "N/A")}{RESET}')
    _hline()
    print(f'  {BOLD}{YELLOW}  ESTATISTICAS DO ARQUIVO{RESET}')
    _hline()
    _row('Tamanho original:', _human(s['original_size']))
    _row('Tamanho comprimido:', _human(s['compressed_size']))
    diff = s['original_size'] - s['compressed_size']
    if diff >= 0:
        _row('Economia:', f'{GREEN}{_human(diff)}{RESET}')
    else:
        _row('Overhead:', f'{RED}{_human(-diff)}{RESET}')
    ratio = s['compression_ratio']
    _row('Taxa de compressao:', f'{GREEN}{BOLD}{ratio}:1{RESET}')
    r = s['reduction_percent']
    if r >= 0:
        _row('Reducao:', f'{GREEN}{BOLD}{r}%{RESET}')
        print(f'  {"":24}{_bar(r)}  {GREEN}{r}%{RESET}')
    else:
        _row('Reducao:', f'{RED}{r}% (arquivo cresceu){RESET}')
    _hline()
    print(f'  {BOLD}{YELLOW}  ALGORITMO SELECIONADO{RESET}')
    _hline()
    _row('Algoritmo:', f'{CYAN}{s.get("strategy", "N/A")}{RESET}')
    all_results = s.get('all_results', {})
    if all_results:
        print(f'  {BOLD}{YELLOW}  COMPARACAO DE ALGORITMOS{RESET}')
        _hline()
        for alg, size in sorted(all_results.items(), key=lambda x: x[1]):
            marker = f' {GREEN}<-- melhor{RESET}' if alg == s.get('strategy') else ''
            pct = (1 - size / s['original_size']) * 100 if s['original_size'] > 0 else 0
            _row(f'  {alg}:', f'{_human(size)} ({pct:.1f}% reducao){marker}')
    _hline()
    _row('SHA-256:', f'{GRAY}{s.get("hash", "N/A")[:32]}...{RESET}')
    _row('Modo:', f'{GREEN}LOSSLESS (sem perdas){RESET}')
    _row('Tempo:', f'{s["time_seconds"]}s')
    _row('Throughput:', f'{s.get("bytes_per_second", 0):,} bytes/s')
    _dline()
    print(f'  {OK} {GREEN}{BOLD}Concluido com sucesso!{RESET}')
    print()


def _print_decompress_universal_stats(s: dict) -> None:
    _header(f'PIED PIPER \u2014 DESCOMPRESSAO UNIVERSAL    {GREEN}{BOLD}[ SEM PERDAS ]{RESET}')
    print()
    _row('Entrada:', f'{WHITE}{s["input_file"]}{RESET}')
    _row('Saida:', f'{WHITE}{s["output_file"]}{RESET}')
    _row('Arquivo original:', f'{CYAN}{s.get("filename", "N/A")}{RESET}')
    _hline()
    print(f'  {BOLD}{YELLOW}  ESTATISTICAS{RESET}')
    _hline()
    _row('Tamanho .PP:', _human(s['pp_size']))
    _row('Tamanho restaurado:', _human(s['restored_size']))
    if s['restored_size'] > 0 and s['pp_size'] > 0:
        ratio = s['restored_size'] / s['pp_size']
        _row('Taxa de expansao:', f'{CYAN}{ratio:.2f}:1{RESET}')
    _row('Algoritmo usado:', f'{CYAN}{s.get("strategy", "N/A")}{RESET}')
    _hline()
    v = s.get('integrity_verified')
    if v is True:
        check = f'{GREEN}\u2714 VERIFICADA \u2013 bytes identicos{RESET}' if _UNICODE else f'{GREEN}OK \u2013 bytes identicos{RESET}'
        _row('Integridade SHA-256:', check)
    elif v is False:
        _row('Integridade SHA-256:', f'{RED}\u2716 FALHOU \u2013 dados corrompidos!{RESET}')
    _row('Tempo:', f'{s["time_seconds"]}s')
    _dline()
    print(f'  {OK} {GREEN}{BOLD}Concluido com sucesso!{RESET}')
    print()


def _print_compress_folder_stats(s: dict) -> None:
    _header('PIED PIPER \u2014 PASTA COMPRIMIDA')
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
    _row('Motor:', e['engine'])
    avail = e['c_engine_available']
    _row('C engine disponivel:', f'{GREEN}Sim{RESET}' if avail else f'{YELLOW}Nao (modo Python puro){RESET}')
    ll = e.get('lossless_available')
    _row('Modo lossless:', f'{GREEN}Disponivel{RESET}' if ll else f'{RED}Indisponivel{RESET}')
    uni = e.get('universal_available')
    _row('Compressao universal:', f'{GREEN}Disponivel{RESET}' if uni else f'{RED}Indisponivel{RESET}')
    _row('Biblioteca:', e['library_path'])
    _row('Linguagens:', e.get('languages', 'N/A'))
    _hline()
    algos = e.get('algorithms', [])
    if algos:
        print(f'  {BOLD}{YELLOW}  ALGORITMOS DISPONIVEIS{RESET}')
        _hline()
        for alg in algos:
            print(f'    {GREEN}\u2022{RESET} {alg}')
    _hline()
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
    cmd_line('pp c <arquivo|pasta> [-q Q] [-l]',         'Comprime QUALQUER arquivo ou pasta \u2192 .PP')
    cmd_line('pp d <arquivo.PP> [-o SAIDA]',             'Descomprime .PP \u2192 arquivo original')
    cmd_line('pp i <arquivo.PP>',                        'Mostra info e estatisticas do .PP')
    cmd_line('pp verify <arquivo>',                      'Verifica integridade (QUALQUER arquivo)')
    cmd_line('pp q <original> <restaurada>',             'Avalia qualidade (imagens)')
    cmd_line('pp q <pasta_orig> <pasta_rest>',           'Compara qualidade de pastas')
    cmd_line('pp engine',                                'Status do motor de compressao')
    cmd_line('pp register',                              'Registra .PP no Windows')
    cmd_line('pp help',                                  'Esta ajuda')
    cmd_line('pp version',                               'Versao')
    print()

    section('EXEMPLOS — QUALQUER ARQUIVO')
    example('pp c relatorio.pdf',               'comprime PDF \u2192 relatorio.PP')
    example('pp c dados.csv',                   'comprime CSV \u2192 dados.PP')
    example('pp c programa.exe',                'comprime executavel \u2192 programa.PP')
    example('pp c musica.wav',                  'comprime audio WAV \u2192 musica.PP')
    example('pp c codigo.py',                   'comprime codigo fonte \u2192 codigo.PP')
    example('pp d relatorio.PP',                'restaura arquivo original identico')
    print()

    section('EXEMPLOS — VERIFICACAO DE INTEGRIDADE')
    example('pp verify foto.png',               'verifica imagem (pixel-perfeito)')
    example('pp verify relatorio.pdf',          'verifica PDF (bytes identicos)')
    example('pp verify dados.csv',              'verifica CSV (bytes identicos)')
    example('pp verify programa.exe',           'verifica executavel (bytes identicos)')
    print(f'    {DIM}O comando verify comprime, descomprime e compara SHA-256{RESET}')
    print(f'    {DIM}para garantir que o arquivo e restaurado perfeitamente.{RESET}')
    print()

    section('EXEMPLOS — IMAGENS')
    example('pp c foto.jpg',                    'lossy, qualidade 75 (padrao)')
    example('pp c foto.jpg -q 90',              'lossy, qualidade alta')
    example('pp c foto.png -l',                 'lossless sem perdas')
    example('pp c foto.bmp -o out.PP',          'saida customizada')
    example('pp d foto.PP',                     'descomprime \u2192 formato original')
    example('pp q foto.jpg foto_restored.png',  'avalia perda de qualidade')
    print()

    section('EXEMPLOS — PASTA INTEIRA')
    example('pp c /meus-arquivos/',     'comprime TODOS os arquivos da pasta')
    example('pp c /fotos/ -l',          'lossless para imagens')
    example('pp d meus-arquivos.PP',    'extrai todos os arquivos')
    print()

    section('MODOS DE COMPRESSAO')
    print(f'    {YELLOW}{BOLD}LOSSY{RESET}     DCT + Quantizacao adaptativa \u2014 maxima reducao, qualidade configuravel')
    print(f'    {GREEN}{BOLD}LOSSLESS{RESET}  Multi-estrategia sem perdas \u2014 pixel-perfeito garantido por SHA-256')
    print()
    print(f'    {DIM}  Estrategias lossless (escolhe a menor automaticamente):{RESET}')
    print(f'    {DIM}  \u2022 stored  \u2014 bytes originais sem re-codificacao (JPEG/WebP ja comprimidos){RESET}')
    print(f'    {DIM}  \u2022 png     \u2014 PNG otimizado em memoria via DEFLATE (ideal para BMP/TIFF){RESET}')
    print(f'    {DIM}  \u2022 dpcm    \u2014 RCT + DPCM espiral + zlib/DEFLATE (fallback){RESET}')
    print()
    print(f'    {DIM}  NOTA: JPEG e WebP em modo lossy sao armazenados sem re-DCT para{RESET}')
    print(f'    {DIM}  evitar dupla compressao lossy. A descompressao gera PNG (DEFLATE).{RESET}')
    print()

    section('QUALIDADE (modo lossy, flag -q)')
    print(f'    {RED}  1-30{RESET}   {_bar(15, 20)}  Maxima compressao')
    print(f'    {YELLOW} 31-60{RESET}   {_bar(45, 20)}  Balanceado')
    print(f'    {CYAN} 61-80{RESET}   {_bar(70, 20)}  Alta qualidade {DIM}(padrao: 75){RESET}')
    print(f'    {GREEN}81-100{RESET}   {_bar(90, 20)}  Quase sem perdas')
    print()

    section('COMPRESSAO UNIVERSAL (nao-imagens)')
    print(f'    {GREEN}{BOLD}QUALQUER ARQUIVO{RESET} e comprimido sem perdas usando o melhor')
    print(f'    algoritmo entre: {CYAN}LZMA (7-Zip), BZ2 (bzip2), DEFLATE (zlib),{RESET}')
    print(f'    {CYAN}BWT+MTF (Burrows-Wheeler), Delta+LZMA{RESET}')
    print(f'    {DIM}Inspirado no 7-Zip e WinRAR. Integridade verificada por SHA-256.{RESET}')
    print()

    section('FORMATOS SUPORTADOS')
    print(f'    {GREEN}{BOLD}Imagens:{RESET} {DIM}PNG, JPEG, BMP, TIFF, GIF, WEBP, ICO, TGA, PPM, PGM, PCX, PSD{RESET}')
    print(f'    {GREEN}{BOLD}Texto:{RESET}   {DIM}TXT, CSV, JSON, XML, HTML, MD, LOG, YAML, INI, CFG{RESET}')
    print(f'    {GREEN}{BOLD}Codigo:{RESET}  {DIM}PY, JS, TS, C, CPP, H, JAVA, RS, GO, RB, PHP, SH{RESET}')
    print(f'    {GREEN}{BOLD}Docs:{RESET}    {DIM}PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX, ODT, RTF{RESET}')
    print(f'    {GREEN}{BOLD}Audio:{RESET}   {DIM}WAV, FLAC, MP3, OGG, AAC, AIFF, WMA{RESET}')
    print(f'    {GREEN}{BOLD}Video:{RESET}   {DIM}MP4, AVI, MKV, MOV, WEBM, FLV, WMV{RESET}')
    print(f'    {GREEN}{BOLD}Outros:{RESET}  {DIM}EXE, DLL, SO, BIN, ZIP, TAR, GZ, 7Z, RAR, e QUALQUER OUTRO{RESET}')
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
    'q': cmd_quality,        'quality': cmd_quality,       'qcheck': cmd_quality,
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
