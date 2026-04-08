#!/usr/bin/env python3
"""
Pied Piper - Executavel unico.

Este script e o ponto de entrada unico para todo o programa Pied Piper.
Ele detecta automaticamente o caminho da instalacao, compila o motor C
se necessario, e executa o CLI.

Uso:
    ./pp c imagem.jpg          Comprime
    ./pp d arquivo.PP          Descomprime
    ./pp i arquivo.PP          Info
    ./pp help                  Ajuda
"""

import os
import sys
import subprocess


def _ensure_engine_built(root: str) -> None:
    """Compila o motor C automaticamente se nao existir."""
    engine_dir = os.path.join(root, 'engine')
    lib_so = os.path.join(engine_dir, 'libmiddleout.so')
    lib_dylib = os.path.join(engine_dir, 'libmiddleout.dylib')

    if os.path.exists(lib_so) or os.path.exists(lib_dylib):
        return

    if not os.path.isdir(engine_dir):
        print("  ERRO: Diretorio engine/ nao encontrado.")
        sys.exit(1)

    print("  [pp] Compilando motor C pela primeira vez...")
    try:
        result = subprocess.run(
            ['make'], cwd=engine_dir, capture_output=True, text=True
        )
        if result.returncode != 0:
            print("  ERRO: Falha ao compilar motor C:")
            print(result.stderr)
            sys.exit(1)
        print("  [pp] Motor C compilado com sucesso.\n")
    except FileNotFoundError:
        print("  ERRO: 'make' nao encontrado. Instale build-essential:")
        print("        sudo apt install build-essential")
        sys.exit(1)


def main() -> int:
    # Resolve caminho do script real (lida com symlinks)
    script_path = os.path.realpath(__file__)
    root = os.path.dirname(script_path)

    # Adiciona ao Python path
    if root not in sys.path:
        sys.path.insert(0, root)

    # Garante que o motor C esta compilado
    _ensure_engine_built(root)

    # Executa CLI
    from pied_piper.cli import main as cli_main
    return cli_main()


if __name__ == '__main__':
    sys.exit(main())
