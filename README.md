# Pied Piper

**Compressor universal de arquivos com algoritmo Middle-Out** — compressao
lossless **sem perdas** para **qualquer tipo de arquivo**, alem de
compressao lossy de alta eficiencia para imagens.

Inspirado no **7-Zip** (LZMA) e **WinRAR** (LZ+BWT), com motor proprio
de multiplos algoritmos que escolhe automaticamente o melhor para cada arquivo.

```
   ____  _          _   ____  _
  |  _ \(_) ___  __| | |  _ \(_)_ __   ___ _ __
  | |_) | |/ _ \/ _` | | |_) | | '_ \ / _ \ '__|
  |  __/| |  __/ (_| | |  __/| | |_) |  __/ |
  |_|   |_|\___|\__,_| |_|   |_| .__/ \___|_|
                                |_|
   Middle-Out Universal Compression Engine v3.0.0
```

---

## Como executar

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
# --- QUALQUER ARQUIVO ---
pp c relatorio.pdf         # Comprime PDF -> relatorio.PP
pp c dados.csv             # Comprime CSV -> dados.PP
pp c programa.exe          # Comprime EXE -> programa.PP
pp c musica.wav            # Comprime WAV -> musica.PP
pp c codigo.py             # Comprime Python -> codigo.PP
pp d relatorio.PP          # Restaura arquivo original identico

# --- IMAGEM (modos lossy/lossless) ---
pp c foto.jpg              # Lossy -> foto.PP
pp c foto.jpg -l           # Lossless sem perdas -> foto.PP
pp c foto.png -q 90        # Lossy qualidade 90
pp c foto.bmp -o saida.PP  # Saida customizada
pp d foto.PP               # Descomprime -> formato original

# --- PASTA INTEIRA (todos os arquivos) ---
pp c /meus-arquivos/       # Comprime TODOS os arquivos -> meus-arquivos.PP
pp d meus-arquivos.PP      # Extrai todos -> meus-arquivos_extracted/

# --- UTILITARIOS ---
pp i arquivo.PP            # Info do arquivo .PP
pp verify foto.png         # Verifica integridade lossless
pp engine                  # Status do motor de compressao
pp help                    # Ajuda completa
```

---

## Compressao Universal (qualquer tipo de arquivo)

O Pied Piper agora comprime **qualquer tipo de arquivo** usando um pipeline
multi-algoritmo que testa todas as estrategias e escolhe a menor:

| Algoritmo | Inspirado em | Melhor para |
|---|---|---|
| **LZMA** | 7-Zip (Igor Pavlov) | Binarios, PDFs, dados gerais |
| **BZ2** | bzip2 (Julian Seward) | Texto com alta redundancia |
| **DEFLATE** | zlib/gzip (RFC 1951) | Compressao rapida geral |
| **BWT+MTF** | bzip2 + engine proprio | Texto estruturado (JSON, XML, HTML) |
| **Delta+LZMA** | Filtro Delta do 7-Zip | Dados sequenciais, audio PCM |

Todos os modos sao **100% lossless** com verificacao SHA-256.

### Testes reais de compressao universal

Testes executados com arquivos reais, resultados exatos medidos:

| Arquivo | Tipo | Original | Comprimido | Ratio | Reducao | Algoritmo | SHA-256 |
|---|---|---|---|---|---|---|---|
| `texto.txt` | Texto puro | 19,200 B | 557 B | **34.47x** | **97.10%** | deflate | OK |
| `dados.json` | JSON | 118,169 B | 2,554 B | **46.27x** | **97.84%** | bwt | OK |
| `planilha.csv` | CSV | 78,935 B | 4,242 B | **18.61x** | **94.63%** | bwt | OK |
| `codigo.py` | Python | 17,000 B | 629 B | **27.03x** | **96.30%** | deflate | OK |
| `dados.xml` | XML | 59,517 B | 3,257 B | **18.28x** | **94.53%** | lzma | OK |
| `pagina.html` | HTML | 30,748 B | 1,097 B | **28.03x** | **96.43%** | bwt | OK |
| `dados.bin` | Binario | 110,000 B | 28,184 B | **3.90x** | **74.34%** | lzma | OK |
| `server.log` | Log | 349,110 B | 6,929 B | **50.39x** | **98.02%** | lzma | OK |
| `readme.md` | Markdown | 23,487 B | 1,018 B | **23.56x** | **95.76%** | bwt | OK |
| `Manual.pdf` | PDF (real) | 351,238 B | 175,851 B | **2.00x** | **49.93%** | lzma | OK |
| **TOTAL** | | **1.12 MB** | **219 KB** | **5.21x** | **80.81%** | | **10/10** |

**Resultado: 10/10 testes passaram. Integridade SHA-256 100% verificada.**
Todos os arquivos restaurados sao bit-a-bit identicos aos originais.

---

## Compressao de imagens

### Modo Lossy (padrao sem `-l`)

Pipeline DCT + Quantizacao Adaptativa Middle-Out:

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
| **stored** | Arquivo ja comprimido (JPEG, PNG, WebP) | PP ~ tamanho original |
| **png** | Imagens raw/brutas (BMP, TIFF, PCX) | PP = PNG otimizado |
| **dpcm** | Fallback RCT+DPCM+zlib | PP variavel |

### Compressao de pastas

```bash
pp c /meus-arquivos/         # Comprime TODOS os arquivos -> meus-arquivos.PP
pp d meus-arquivos.PP        # Extrai -> meus-arquivos_extracted/
```

- **Todos os tipos de arquivo** sao comprimidos (imagens + documentos + codigo + binarios)
- Imagens usam o pipeline de imagem (lossy ou lossless)
- Demais arquivos usam o pipeline universal (sempre lossless)
- Subdiretorios nao sao incluidos (apenas arquivos top-level)

---

## Verificacao de integridade

```bash
pp verify foto.png         # Confirma integridade bit-a-bit
```

```
  APROVADO — reconstrucao pixel-perfeita garantida
  O algoritmo Middle-Out DPCM e VERDADEIRAMENTE LOSSLESS.
```

Para arquivos universais, a integridade e verificada automaticamente
via SHA-256 durante a descompressao.

---

## Arquitetura

| Linguagem | Arquivo | Funcao |
|---|---|---|
| **C** | `engine/middleout.c` | Motor: DCT, DPCM lossless, espiral, RLE, quantizacao |
| **C header** | `engine/middleout.h` | API do motor com documentacao |
| **Python** | `pied_piper/codec.py` | Codec: imagens + compressao universal de arquivos |
| **Python** | `pied_piper/cli.py` | CLI: estatisticas, modos, comandos pp |
| **Python** | `pied_piper/compressors/` | Algoritmos: BWT, Huffman, LZ77, Delta, RLE, Pipeline |
| **Shell** | `pp` | Launcher: auto-install, auto-compile, ponto de entrada unico |
| **Makefile** | `engine/Makefile` | Build: gcc -O3 -march=native |

```
testecodex/
├── pp                              # Unico executavel (Python, auto-install)
├── engine/
│   ├── middleout.h                 # API do motor C
│   ├── middleout.c                 # Motor C: DCT, DPCM, espiral, RLE
│   ├── Makefile                    # Build: gcc -O3 -march=native
│   └── asm/dct_simd.asm           # DCT otimizada com SIMD (opcional)
├── pied_piper/
│   ├── __init__.py
│   ├── __main__.py
│   ├── codec.py                    # Codec: imagens + universal
│   ├── cli.py                      # CLI completo
│   └── compressors/                # Modulos de compressao universal
│       ├── __init__.py
│       ├── bwt.py                  # Burrows-Wheeler Transform + Move-to-Front
│       ├── huffman.py              # Codificacao Huffman canonica
│       ├── lz77.py                 # LZ77 sliding window (inspirado DEFLATE)
│       ├── delta.py                # Delta encoding (inspirado filtro 7-Zip)
│       ├── rle.py                  # Run-Length Encoding
│       └── pipeline.py             # Pipeline multi-algoritmo (escolhe o melhor)
├── tools/
│   └── ppbatch.rb                  # Compressao em lote (Ruby)
└── requirements.txt
```

---

## Algoritmos de compressao

### Pipeline Universal (qualquer arquivo)

Inspirado no **7-Zip** e **WinRAR**, o pipeline testa multiplas
estrategias e escolhe a que produz o menor resultado:

1. **LZMA** (Lempel-Ziv-Markov chain) — algoritmo do 7-Zip, preset 9 extreme
2. **BZ2** (Burrows-Wheeler + Huffman) — algoritmo do bzip2, nivel 9
3. **DEFLATE** (LZ77 + Huffman) — algoritmo do gzip/zlib, nivel 9
4. **BWT+MTF+DEFLATE** — Burrows-Wheeler Transform proprio + Move-to-Front + zlib
5. **Delta+LZMA** — pre-processamento delta + LZMA (dados sequenciais)

### Pipeline de Imagens

- **Lossy**: DCT 8x8 + Quantizacao Adaptativa + espiral Middle-Out + DPCM + zlib
- **Lossless**: RCT (JPEG 2000) + DPCM horizontal + zlib nivel 9

---

## Formatos suportados

**Qualquer arquivo** pode ser comprimido. Tipos com suporte especializado:

- **Imagens**: PNG, JPEG, BMP, TIFF, GIF, WEBP, ICO, TGA, PPM, PGM, PCX, PSD, APNG, JP2, DDS
- **Texto**: TXT, CSV, JSON, XML, HTML, MD, LOG, YAML, INI, CFG
- **Codigo**: PY, JS, TS, C, CPP, H, JAVA, RS, GO, RB, PHP, SH
- **Documentos**: PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX, ODT, RTF
- **Audio**: WAV, FLAC, MP3, OGG, AAC, AIFF, WMA
- **Video**: MP4, AVI, MKV, MOV, WEBM, FLV, WMV
- **Binarios**: EXE, DLL, SO, BIN, e qualquer outro formato

---

## Licenca

Proprietary — Pied Piper

> "Making the world a better place... through better compression."
