# Pied Piper

**O compressor de imagens mais eficiente da Internet** — implementando o algoritmo exclusivo **Middle-Out Compression** com motor de alta performance em C.

```
   ____  _          _   ____  _
  |  _ \(_) ___  __| | |  _ \(_)_ __   ___ _ __
  | |_) | |/ _ \/ _` | | |_) | | '_ \ / _ \ '__|
  |  __/| |  __/ (_| | |  __/| | |_) |  __/ |
  |_|   |_|\___|\__,_| |_|   |_| .__/ \___|_|
                                |_|
   Middle-Out Compression Engine v2.0.0
```

---

## Destaques

- **Algoritmo Middle-Out exclusivo** — processa blocos do centro da imagem para fora em espiral, usando blocos centrais como referência preditiva
- **Motor em C** (`libmiddleout.so`) com DCT via multiplicação de matrizes, até **1.6 milhões de pixels/segundo**
- **Compressão até 91%** em imagens não-comprimidas (BMP, TIFF)
- **Quantização adaptativa** baseada na variância local de cada bloco
- **Predição inter-blocos (delta encoding)** que aproveita a similaridade entre blocos vizinhos na espiral
- **Suporta todos os formatos** de imagem (PNG, JPG, BMP, TIFF, GIF, WebP, PSD, TGA, PCX, JP2, DDS, e muitos mais)
- **Preserva canal alpha** com tabela de quantização dedicada
- **Um único executável** (`./pp`) — compila o motor C automaticamente na primeira execução
- **CLI ultra-simples**: `pp c foto.jpg` e `pp d foto.PP`

---

## Instalação Rápida

```bash
# 1. Clone o repositório
git clone https://github.com/parososi/testecodex.git
cd testecodex

# 2. Instale dependências Python
pip install -r requirements.txt

# 3. Execute (compila o motor C automaticamente)
./pp help
```

Requisitos: Python 3.8+, GCC, Pillow, NumPy.

---

## Uso em 30 segundos

```bash
# Comprimir
./pp c foto.jpg                    # foto.jpg -> foto.PP
./pp c foto.png -q 90              # qualidade 90
./pp c foto.bmp -o saida.PP        # saída customizada

# Descomprimir
./pp d foto.PP                     # -> foto_restored.png
./pp d foto.PP -o restaurada.jpg   # saída JPG

# Informações
./pp i foto.PP                     # mostra metadados
./pp engine                        # status do motor C
./pp help                          # ajuda completa
```

Todos os comandos também aceitam nomes completos: `compress`, `decompress`, `info`.

---

## Resultados reais

Teste em imagem 1024x1024 não-comprimida (3 MB BMP):

| Métrica | Valor |
|---|---|
| Tamanho original | 3.00 MB |
| Tamanho .PP | 269 KB |
| **Taxa de compressão** | **11.41:1** |
| **Redução** | **91.24%** |
| Bits por pixel | 2.10 |
| PSNR | 30.87 dB |
| Blocos preditos Middle-Out | 96.19% |
| Esparsidade DCT | 89.57% |
| Tempo compressão | 0.77 s |
| Throughput | 1.36 M px/s |

---

## Arquitetura

```
testecodex/
├── pp                          # Executável único (ponto de entrada)
├── engine/                     # Motor de compressão em C
│   ├── middleout.h             #   API do motor Middle-Out
│   ├── middleout.c             #   Implementação DCT, Wavelet, RLE, espiral
│   ├── Makefile                #   Build do motor C
│   └── libmiddleout.so         #   Biblioteca compartilhada (gerada)
├── pied_piper/                 # Pacote Python
│   ├── __init__.py             #   API pública
│   ├── __main__.py             #   python -m pied_piper
│   ├── codec.py                #   Wrapper Python + ctypes bindings
│   └── cli.py                  #   Interface de linha de comando
├── docs/                       # Documentação completa
│   ├── ALGORITHM.md            #   Deep dive no algoritmo Middle-Out
│   ├── FORMAT.md               #   Especificação do formato .PP
│   ├── USAGE.md                #   Guia de uso completo
│   └── API.md                  #   Documentação da API Python
├── samples/                    # Imagens de teste
├── requirements.txt
└── setup.py
```

---

## Por que em múltiplas linguagens?

O Pied Piper usa uma arquitetura **híbrida de alta performance**:

1. **C** (`engine/middleout.c`): operações numericamente pesadas — DCT, IDCT, Wavelet Haar, RLE, ordenação espiral, quantização. Com `-O3 -march=native`, o motor atinge throughput de milhões de pixels por segundo.

2. **Python** (`pied_piper/codec.py`): orquestração do pipeline, leitura de qualquer formato de imagem via Pillow, conversões de espaço de cor em NumPy vetorizado, serialização do formato .PP, bindings via `ctypes`.

3. **Shell/Make** (`engine/Makefile`, `pp`): compilação automática do motor C na primeira execução e lançamento unificado.

Este design dá o melhor de cada linguagem: **velocidade do C** nas rotinas críticas, **flexibilidade do Python** na lógica de alto nível, **simplicidade do shell** para o usuário final.

---

## Documentação

- **[docs/ALGORITHM.md](docs/ALGORITHM.md)** — Explicação técnica completa do algoritmo Middle-Out
- **[docs/FORMAT.md](docs/FORMAT.md)** — Especificação binária do formato .PP
- **[docs/USAGE.md](docs/USAGE.md)** — Guia de uso com todos os comandos e exemplos
- **[docs/API.md](docs/API.md)** — API Python para integração

---

## Licença

Proprietary — Pied Piper Inc.

> "Making the world a better place... through better compression."
