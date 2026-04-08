# Pied Piper

**O compressor de imagens com algoritmo Middle-Out** — implementando compressao
lossy e **lossless sem perdas** usando motor de alta performance em C.

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

Para executar com duplo-clique em gerenciadores de arquivo, marque o arquivo
como executavel (`chmod +x pp`) e configure o gerenciador para "Executar no
terminal".

---

## Comandos

```bash
pp c foto.jpg              # Lossy -> foto.PP
pp c foto.png -l           # LOSSLESS sem perdas -> foto.PP
pp c foto.png -q 90        # Lossy qualidade 90
pp c foto.bmp -o saida.PP  # Saida customizada

pp d foto.PP               # Descomprime -> foto_restored.png
pp d foto.PP -o res.jpg    # Saida JPG

pp i foto.PP               # Info: dimensoes, modo, qualidade
pp verify foto.png         # Verifica integridade lossless
pp engine                  # Status do motor C
pp help                    # Ajuda completa
```

Todos os comandos comecam com `pp`. Aliases: `compress`/`c`, `decompress`/`d`,
`info`/`i`, `check`/`verify`.

---

## Dois modos de compressao

### Modo Lossy (padrao)

Pipeline DCT + Quantizacao Adaptativa + Espiral Middle-Out:

1. RGB -> YCbCr (separacao luminancia/crominancia)
2. Subamostragem crominancia 4:2:0
3. Ordenacao de blocos em **espiral Middle-Out** (centro -> borda)
4. DCT 8x8 via multiplicacao de matrizes pre-computada
5. **Quantizacao adaptativa** por variancia local do bloco
6. Delta prediction entre blocos consecutivos na espiral
7. Zigzag + RLE + zlib

| Metrica | Valor (teste 1024x1024 BMP) |
|---|---|
| Tamanho original | 3.00 MB |
| Tamanho .PP | 269 KB |
| **Taxa de compressao** | **11.41:1** |
| **Reducao** | **91.24%** |
| Blocos preditos Middle-Out | 96.19% |
| Throughput | 1.36 M px/s |

### Modo Lossless (`-l`)

Pipeline Middle-Out DPCM + Transformada de Cor Reversivel (RCT):

1. RGB -> RCT (Y, Co, Cg) — **completamente reversivel, sem perdas**
2. Ordenacao de blocos em **espiral Middle-Out** (mesmo centro -> borda)
3. **DPCM entre blocos** na ordem espiral: residuais = bloco_atual - bloco_anterior
4. RLE dos residuais int16
5. zlib nivel 9
6. Verificacao **SHA-256** garante reconstrucao pixel-perfeita

```bash
pp c foto.png -l           # Comprime
pp d foto.PP               # Descomprime (mostra: LOSSLESS - perfeito)
pp verify foto.png         # Confirma integridade bit-a-bit
```

A saida inclui:
```
  PSNR:                 LOSSLESS (perfeito)
  Integridade SHA-256:  VERIFICADA - pixels identicos ao original
```

---

## O algoritmo Middle-Out e inovador?

**Avaliacao honesta:**

O nome "Middle-Out" foi inspirado na serie Silicon Valley. A implementacao real
tem elementos genuinamente originais e outros baseados em tecnicas conhecidas:

| Componente | Originalidade |
|---|---|
| **Espiral do centro para as bordas** | Original — nenhum codec padrão (JPEG, PNG, HEVC) usa esta ordem |
| **DPCM entre blocos na espiral** | Original — PNG usa predicao por scanline, JPEG-LS usa predicao pixel-a-pixel |
| **Quantizacao adaptativa por variancia** | Presente em codecs modernos (HEVC, AV1), mas implementacao propria |
| **DCT 8x8** | Identico ao JPEG — tecnica de 1974 |
| **RCT (Transformada de Cor Reversivel)** | Padrao JPEG 2000, usada aqui para o modo lossless |
| **Subamostragem 4:2:0** | Identico ao JPEG |

**O que e genuinamente inovador:**
- A **ordenacao em espiral do centro** para predicao DPCM e diferente de
  qualquer codec amplamente documentado. A hipotese e que imagens naturais
  tem maior correlacao radial (o sujeito no centro e mais similar ao centro
  do que as bordas entre si).
- O modo **lossless com DPCM na espiral Middle-Out** e distinto do PNG
  (predicao por scanline horizontal) e do JPEG-LS (predicao por pixel com
  contexto adaptativo).

**O que nao e inovador:**
- A base matematica (DCT, quantizacao, RLE, zlib) e tecnica estabelecida.
- Nao houve avaliacao peer-reviewed comparando com FLIF, AVIF lossless, ou
  WebP lossless em benchmarks padrao.

---

## Arquitetura multi-linguagem

O Pied Piper usa **6 linguagens** cada uma onde e mais eficiente:

| Linguagem | Arquivo | Funcao |
|---|---|---|
| **C** | `engine/middleout.c` | Motor: DCT, DPCM lossless, espiral, RLE, quantizacao |
| **C header** | `engine/middleout.h` | API do motor com documentacao |
| **Python** | `pied_piper/codec.py` | Codec: RCT, bindings ctypes, zlib, SHA-256 |
| **Python** | `pied_piper/cli.py` | CLI: estatisticas, modos, comandos pp* |
| **Shell** | `pp` | Launcher: auto-install, auto-compile, ponto de entrada unico |
| **Makefile** | `engine/Makefile` | Build: gcc -O3 -march=native |
| **NASM x86-64** | `engine/asm/dct_simd.asm` | DCT otimizada SIMD (opcional, documentada) |
| **Ruby** | `tools/ppbatch.rb` | Compressao em lote + relatorio HTML |

```
testecodex/
├── pp                          # Unico executavel (Python, auto-install)
├── engine/
│   ├── middleout.h             # API C (header)
│   ├── middleout.c             # Motor C: lossy + lossless
│   ├── Makefile                # Build gcc
│   └── asm/
│       └── dct_simd.asm        # DCT otimizada NASM x86-64 (opcional)
├── pied_piper/
│   ├── __init__.py             # Versao 3.0.0
│   ├── __main__.py             # python -m pied_piper
│   ├── codec.py                # Codec Python + ctypes
│   └── cli.py                  # CLI (comandos pp*)
├── tools/
│   └── ppbatch.rb              # Lote em Ruby
├── docs/
│   ├── ALGORITHM.md
│   ├── FORMAT.md
│   ├── USAGE.md
│   └── API.md
└── requirements.txt
```

---

## Estatisticas exibidas apos compressao

Apos `pp c foto.jpg`, o programa exibe:

```
================================================================
   PIED PIPER - COMPRESSAO CONCLUIDA  [   LOSSY    ]
================================================================
  Entrada:              foto.jpg
  Saida:                foto.PP
  Formato original:     JPEG (RGB)
  Dimensoes:            1024 x 1024 pixels
  Total de pixels:      1,048,576
  Megapixels:           1.049 MP
  Canal Alpha:          Nao
  Tamanho original:     3.00 MB
  Tamanho comprimido:   269.00 KB
  Taxa de compressao:   11.41:1
  Bits por pixel:       2.10
  Reducao:              91.24%
                        [####################################....]
  ALGORITMO MIDDLE-OUT - ESTATISTICAS INTERNAS
  Modo:                 LOSSY - DCT + Quantizacao adaptativa
  Qualidade:            75/100
  PSNR:                 N/A (use pp d para calcular)
  Blocos processados:   12,288
  Blocos preditos:      11,820 (96.19%)
  Blocos vazios:        1,843 (14.99%)
  Esparsidade residual: 89.57%
  Tempo:                0.77s
  Throughput:           1,361,788 px/s
================================================================
```

No modo lossless (`-l`):

```
================================================================
   PIED PIPER - COMPRESSAO CONCLUIDA  [ SEM PERDAS ]
================================================================
  ...
  PSNR:                 LOSSLESS (perfeito)
  Integridade SHA-256:  VERIFICADA - pixels identicos ao original
================================================================
```

---

## Formatos suportados

PNG, JPEG, BMP, TIFF, GIF, WEBP, ICO, TGA, PPM, PGM, PCX, PSD,
APNG, JP2, DDS, e todos os formatos suportados pela biblioteca Pillow.

---

## Licenca

Proprietary — Pied Piper

> "Making the world a better place... through better compression."
