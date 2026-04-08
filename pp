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


# ---------------------------------------------------------------------------
# Instalacao automatica de dependencias Python
# ---------------------------------------------------------------------------

_REQUIRED = [('PIL', 'Pillow'), ('numpy', 'numpy')]


def _ensure_pip_deps() -> None:
    """Instala Pillow e numpy via pip se nao estiverem disponiveis."""
    missing = []
    for import_name, pip_name in _REQUIRED:
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pip_name)

    if not missing:
        return

    print(f"  [pp] Instalando dependencias: {', '.join(missing)} ...")
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '--quiet'] + missing,
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"  [pp] AVISO: pip retornou erro:\n{result.stderr}")
            print(f"  [pp] Tente manualmente: pip install {' '.join(missing)}")
        else:
            print(f"  [pp] Dependencias instaladas com sucesso.\n")
    except Exception as e:
        print(f"  [pp] AVISO: nao foi possivel instalar automaticamente: {e}")
        print(f"  [pp] Instale manualmente: pip install {' '.join(missing)}")


# ---------------------------------------------------------------------------
# Compilacao automatica do motor C
# ---------------------------------------------------------------------------

def _ensure_engine_built(root: str) -> None:
    """Compila libmiddleout automaticamente se nao existir."""
    engine_dir = os.path.join(root, 'engine')

    candidates = [
        os.path.join(engine_dir, 'libmiddleout.so'),
        os.path.join(engine_dir, 'libmiddleout.dylib'),
    ]
    if any(os.path.exists(p) for p in candidates):
        return

    if not os.path.isdir(engine_dir):
        print("  ERRO: Diretorio engine/ nao encontrado.")
        print("  Execute este script a partir do diretorio do Pied Piper.")
        sys.exit(1)

    print("  [pp] Compilando motor C pela primeira vez...")
    try:
        result = subprocess.run(
            ['make'], cwd=engine_dir,
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print("  ERRO: Falha ao compilar motor C:")
            print(result.stderr)
            print()
            print("  Verifique se gcc/make estao instalados:")
            print("    Linux:  sudo apt install build-essential")
            print("    Mac:    xcode-select --install")
            sys.exit(1)
        print("  [pp] Motor C compilado com sucesso.\n")
    except FileNotFoundError:
        print("  ERRO: 'make' nao encontrado.")
        print("  Linux:  sudo apt install build-essential")
        print("  Mac:    xcode-select --install")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------

def main() -> int:
    # Resolve caminho real (funciona com symlinks e duplo-clique)
    script_path = os.path.realpath(__file__)
    root = os.path.dirname(script_path)

    # Adiciona raiz do projeto ao Python path
    if root not in sys.path:
        sys.path.insert(0, root)

    # Instala dependencias se necessario
    _ensure_pip_deps()

    # Compila motor C se necessario
    _ensure_engine_built(root)

    # Executa CLI
    from pied_piper.cli import main as cli_main
    return cli_main()


if __name__ == '__main__':
    sys.exit(main())
