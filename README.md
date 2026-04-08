# Pied Piper

**O compressor de imagens com algoritmo Middle-Out** — compressao
lossless **verdadeiramente sem perdas** e lossy de alta eficiencia,
usando motor de alta performance em C.

```
   ____  _          _   ____  _
  |  _ \(_) ___  __| | |  _ \(_)_ __   ___ _ __
  | |_) | |/ _ \/ _` | | |_) | | '_ \ / _ \ '__|
  |  __/| |  __/ (_| | |  __/| | |_) |  __/ |
  |_|   |_|\___|\__,_| |_|   |_| .__/ \___|_|
                                |_|
   Middle-Out Lossless/Lossy Engine v3.0.0
```

---

## Como executar (unico arquivo)

```bash
# 1. Clone
git clone https://github.com/parososi/testecodex.git
cd testecodex

# 2. Execute diretamente — instala dependencias e compila automaticamente
./pp help
```

**Sem configuracao manual.** O `pp` detecta dependencias ausentes, instala via
`pip`, e compila o motor C com `gcc` na primeira execucao.

---

## Comandos

```bash
# --- IMAGEM INDIVIDUAL ---
pp c foto.jpg              # Lossy -> foto.PP
pp c foto.jpg -l           # Lossless sem perdas -> foto.PP (auto-escolhe melhor estrategia)
pp c foto.png -q 90        # Lossy qualidade 90
pp c foto.bmp -o saida.PP  # Saida customizada

pp d foto.PP               # Descomprime -> formato original (ex: foto_restored.jpg)
pp d foto.PP -o res.png    # Saida em formato especifico

# --- PASTA INTEIRA ---
pp c /fotos/               # Comprime todas as imagens -> fotos.PP (bundle lossless)
pp c /fotos/ -l            # Lossless explicito (padrao para pastas)
pp c /fotos/ -q 80         # Lossy para toda a pasta
pp c /fotos/ -o backup.PP  # Saida customizada

pp d fotos.PP              # Extrai todas as imagens -> fotos_extracted/
pp d fotos.PP -o /destino/ # Extrai para pasta especifica

# --- UTILITARIOS ---
pp i foto.PP               # Info: dimensoes, modo, estrategia
pp verify foto.png         # Verifica integridade lossless
pp engine                  # Status do motor C
pp help                    # Ajuda completa
```

---

## Dois modos de compressao

### Modo Lossy (padrao sem `-l`)

Pipeline DCT + Quantizacao Adaptativa:

1. RGB -> YCbCr (separacao luminancia/crominancia)
2. Subamostragem crominancia 4:2:0
3. DCT 8x8 + quantizacao adaptativa por variancia
4. Zigzag + planos de frequencia + DPCM DC
5. zlib nivel 9

| Metrica | Valor (teste 1024x1024 BMP) |
|---|---|
| Tamanho original | 3.00 MB |
| Tamanho .PP | 269 KB |
| **Taxa de compressao** | **11.41:1** |
| **Reducao** | **91.24%** |
| Throughput | 1.36 M px/s |

### Modo Lossless (`-l`) — Multi-estrategia sem perdas

O modo lossless escolhe automaticamente entre **3 estrategias** e usa a
que produz o **menor arquivo**, sempre garantindo reconstrucao pixel-perfeita
verificada por SHA-256.

| Estrategia | Quando e usada | Resultado |
|---|---|---|
| **stored** | Arquivo ja comprimido (JPEG, PNG, WebP) | PP ≈ tamanho original |
| **png** | Imagens raw/brutas (BMP, TIFF, PCX) | PP = PNG otimizado |
| **dpcm** | Fallback RCT+DPCM+zlib | PP variavel |

```bash
# JPEG (6.92 MB)
pp c foto.jpg -l   # -> estrategia 'stored': PP ≈ 6.92 MB
pp d foto.PP       # -> foto_restored.jpg (identico ao original, mesmo tamanho)

# BMP (53 MB raw)
pp c foto.bmp -l   # -> estrategia 'png': PP ≈ 14 MB
pp d foto.PP       # -> foto_restored.png (pixel-perfeito)
```

A saida de descompressao lossless inclui:
```
  Estrategia:           Bytes originais (sem re-codificacao)
  PSNR:                 LOSSLESS (perfeito)
  Integridade SHA-256:  VERIFICADA - pixels identicos ao original
```

### Compressao de pastas

```bash
pp c /minhas-fotos/          # Comprime todas as imagens -> minhas-fotos.PP
pp d minhas-fotos.PP         # Extrai -> minhas-fotos_extracted/
```

- Arquivos que **nao sao imagens** sao **ignorados automaticamente**
- Subdiretorios nao sao incluidos (apenas arquivos top-level)
- Ao descompactar mais de uma imagem, os arquivos vao para uma pasta
- Cada imagem e comprimida individualmente e empacotada no bundle

---

## Verificacao de integridade

```bash
pp verify foto.png         # Confirma integridade bit-a-bit
```

```
  APROVADO — reconstrucao pixel-perfeita garantida
  O algoritmo Middle-Out DPCM e VERDADEIRAMENTE LOSSLESS.
```

---

## Arquitetura

| Linguagem | Arquivo | Funcao |
|---|---|---|
| **C** | `engine/middleout.c` | Motor: DCT, DPCM lossless, espiral, RLE, quantizacao |
| **C header** | `engine/middleout.h` | API do motor com documentacao |
| **Python** | `pied_piper/codec.py` | Codec: RCT, bindings ctypes, zlib, SHA-256, bundle |
| **Python** | `pied_piper/cli.py` | CLI: estatisticas, modos, comandos pp* |
| **Shell** | `pp` | Launcher: auto-install, auto-compile, ponto de entrada unico |
| **Makefile** | `engine/Makefile` | Build: gcc -O3 -march=native |

```
testecodex/
├── pp                          # Unico executavel (Python, auto-install)
├── engine/
│   ├── middleout.h
│   ├── middleout.c
│   ├── Makefile
│   └── asm/dct_simd.asm
├── pied_piper/
│   ├── __init__.py
│   ├── __main__.py
│   ├── codec.py                # Codec: compress, decompress, compress_folder, decompress_bundle
│   └── cli.py
└── requirements.txt
```

---

## Formatos suportados

PNG, JPEG, BMP, TIFF, GIF, WEBP, ICO, TGA, PPM, PGM, PCX, PSD,
APNG, JP2, DDS, e todos os formatos suportados pela biblioteca Pillow.

---

## Licenca

Proprietary — Pied Piper

> "Making the world a better place... through better compression."
