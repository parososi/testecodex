#!/usr/bin/env python3
"""
Pied Piper - Executavel unico.

Clique duas vezes ou execute no terminal:
    ./pp help          Ajuda
    ./pp c foto.jpg    Comprime (lossy)
    ./pp c foto.png -l Comprime (lossless, sem perdas)
    ./pp d foto.PP     Descomprime
    ./pp verify foto   Verifica integridade lossless

Este script instala dependencias Python automaticamente se necessario,
compila o motor C na primeira execucao, e roda o CLI Pied Piper.

Lingagens usadas neste projeto:
  C         - motor de compressao (DCT, DPCM, RLE, espiral Middle-Out)
  Python    - codec, CLI, bindings ctypes, conversoes de cor
  Shell     - launcher, automacao de build
  NASM x86  - DCT otimizada com instrucoes SIMD (opcional, engine/dct_simd.asm)
  Ruby      - utilitario de compressao em lote (tools/ppbatch.rb)
  Makefile  - build system do motor C
"""

import os
import sys
import subprocess
import threading
import time


# ---------------------------------------------------------------------------
# Cores ANSI (Windows 10+ nativo, sem dependencias extras)
# ---------------------------------------------------------------------------

def _enable_win_ansi():
    """Ativa suporte ANSI no terminal Windows sem dependencias externas."""
    if sys.platform == 'win32':
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            handle = k32.GetStdHandle(-11)          # STD_OUTPUT_HANDLE
            mode = ctypes.c_ulong()
            k32.GetConsoleMode(handle, ctypes.byref(mode))
            k32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        except Exception:
            pass


_enable_win_ansi()
_COLOR = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()


def _c(code):
    return code if _COLOR else ''


def _has_unicode():
    enc = getattr(sys.stdout, 'encoding', None) or 'ascii'
    try:
        '\u2714\u2716\u283b'.encode(enc)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


_UNICODE = _COLOR and _has_unicode()

RESET  = _c('\033[0m')
BOLD   = _c('\033[1m')
DIM    = _c('\033[2m')
CYAN   = _c('\033[96m')
GREEN  = _c('\033[92m')
YELLOW = _c('\033[93m')
RED    = _c('\033[91m')
GRAY   = _c('\033[90m')
WHITE  = _c('\033[97m')

_OK   = f'{GREEN}\u2714{RESET}' if _UNICODE else f'{GREEN}OK{RESET}'
_FAIL = f'{RED}\u2716{RESET}'   if _UNICODE else f'{RED}ERRO{RESET}'


# ---------------------------------------------------------------------------
# Spinner animado para a fase de instalacao
# ---------------------------------------------------------------------------

class _Spinner:
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
        clear = ' ' * (len(self.msg) + 10)
        sys.stdout.write(f'\r{clear}\r')
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
        icon = _OK if ok else _FAIL
        print(f'  {icon} {final}')


# ---------------------------------------------------------------------------
# Instalacao automatica de dependencias Python (sem permissao de admin)
# ---------------------------------------------------------------------------

_REQUIRED = [('PIL', 'Pillow'), ('numpy', 'numpy')]


def _ensure_pip_deps() -> None:
    """Instala dependencias via pip --user (sem necessidade de admin/sudo)."""
    missing = []
    for import_name, pip_name in _REQUIRED:
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pip_name)

    if not missing:
        return

    pkgs_str = ', '.join(missing)
    print()
    print(f'  {CYAN}{BOLD}Pied Piper{RESET} {DIM}\u2013 Configuracao inicial{RESET}')
    print()

    sp = _Spinner(f'Instalando {pkgs_str}...')
    sp.start()

    # Estrategia 1: --user (nao exige admin, instala na pasta do usuario)
    # Estrategia 2: sem --user (funciona dentro de virtualenv)
    strategies = [
        [sys.executable, '-m', 'pip', 'install', '--user', '--quiet'] + missing,
        [sys.executable, '-m', 'pip', 'install', '--quiet'] + missing,
    ]

    for cmd in strategies:
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if proc.returncode == 0:
                sp.stop(True, f'{pkgs_str} instalado com sucesso!')
                print()
                return
        except Exception:
            continue

    sp.stop(False, 'Instalacao automatica falhou.')
    print()
    print(f'  {YELLOW}Solucao:{RESET} Execute no terminal:')
    print(f'    pip install --user {" ".join(missing)}')
    print()


# ---------------------------------------------------------------------------
# Compilacao automatica do motor C
# ---------------------------------------------------------------------------

def _ensure_engine_built(root: str) -> None:
    """Compila libmiddleout automaticamente se nao existir."""
    engine_dir = os.path.join(root, 'engine')

    candidates = [
        os.path.join(engine_dir, 'libmiddleout.so'),
        os.path.join(engine_dir, 'libmiddleout.dylib'),
        os.path.join(engine_dir, 'libmiddleout.dll'),
    ]
    if any(os.path.exists(p) for p in candidates):
        return

    if not os.path.isdir(engine_dir):
        return

    # No Windows, 'make' geralmente nao esta disponivel — usa Python puro
    if sys.platform == 'win32':
        return

    try:
        subprocess.run(
            ['make'], cwd=engine_dir,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pass  # make nao encontrado — fallback Python sera usado automaticamente


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------

def main() -> int:
    script_path = os.path.realpath(__file__)
    root = os.path.dirname(script_path)

    if root not in sys.path:
        sys.path.insert(0, root)

    _ensure_pip_deps()
    _ensure_engine_built(root)

    from pied_piper.cli import main as cli_main
    return cli_main()


if __name__ == '__main__':
    sys.exit(main())
