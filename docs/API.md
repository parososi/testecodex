# API Python do Pied Piper

O Pied Piper pode ser usado diretamente como uma biblioteca Python para integração em outros programas.

## 1. Importação

```python
from pied_piper import compress, decompress, info
```

Ou importando o módulo completo:

```python
from pied_piper import codec
```

## 2. Funções Principais

### `compress(input_path, output_path=None, quality=75) → dict`

Comprime uma imagem para o formato .PP.

**Parâmetros:**
- `input_path` (str): Caminho da imagem de entrada. Qualquer formato suportado pelo Pillow.
- `output_path` (str, opcional): Caminho do arquivo .PP de saída. Se omitido, usa o mesmo nome da entrada com extensão `.PP`.
- `quality` (int, padrão 75): Qualidade de compressão, de 1 (máxima compressão) a 100 (quase sem perdas).

**Retorna:** Dicionário com estatísticas detalhadas da compressão.

**Exemplo:**

```python
from pied_piper import compress

stats = compress("foto.jpg", "foto.PP", quality=85)

print(f"Redução: {stats['reduction_percent']}%")
print(f"Taxa: {stats['compression_ratio']}:1")
print(f"Bits por pixel: {stats['bits_per_pixel']}")
print(f"Blocos preditos: {stats['prediction_percent']}%")
```

**Campos do dicionário retornado:**

| Campo | Tipo | Descrição |
|---|---|---|
| `input_file` | str | Caminho da entrada |
| `output_file` | str | Caminho da saída .PP |
| `original_format` | str | Formato detectado da imagem original |
| `original_mode` | str | Modo de cor original (RGB, RGBA, etc.) |
| `width` | int | Largura em pixels |
| `height` | int | Altura em pixels |
| `total_pixels` | int | Número total de pixels |
| `megapixels` | float | Megapixels (arredondado) |
| `has_alpha` | bool | Se possui canal alpha |
| `original_size` | int | Tamanho do arquivo original em bytes |
| `compressed_size` | int | Tamanho do .PP em bytes |
| `compression_ratio` | float | Taxa de compressão (ex: 11.41) |
| `reduction_percent` | float | Percentual de redução |
| `bits_per_pixel` | float | Densidade do arquivo comprimido |
| `quality` | int | Qualidade usada |
| `time_seconds` | float | Tempo total de compressão |
| `pixels_per_second` | int | Throughput |
| `total_blocks` | int | Número de blocos 8x8 processados |
| `predicted_blocks` | int | Blocos codificados por delta Middle-Out |
| `prediction_percent` | float | % de blocos com predição |
| `zero_blocks` | int | Blocos completamente zerados |
| `zero_blocks_percent` | float | % de blocos vazios |
| `coefficient_sparsity` | float | % de coeficientes DCT zerados |

### `decompress(input_path, output_path=None) → dict`

Descomprime um arquivo .PP de volta para imagem.

**Parâmetros:**
- `input_path` (str): Caminho do arquivo .PP.
- `output_path` (str, opcional): Caminho da imagem de saída. Se omitido, usa o mesmo nome com sufixo `_restored.png`. O formato é detectado pela extensão.

**Retorna:** Dicionário com estatísticas da descompressão.

**Exemplo:**

```python
from pied_piper import decompress

stats = decompress("foto.PP", "foto_restored.jpg")

print(f"Dimensões: {stats['width']}x{stats['height']}")
print(f"Tempo: {stats['time_seconds']}s")
```

**Campos retornados:**

| Campo | Tipo | Descrição |
|---|---|---|
| `input_file` | str | Arquivo .PP de entrada |
| `output_file` | str | Imagem de saída |
| `original_format` | str | Formato original (do header) |
| `width` | int | Largura |
| `height` | int | Altura |
| `total_pixels` | int | Pixels totais |
| `megapixels` | float | MP |
| `has_alpha` | bool | Tem alpha |
| `pp_size` | int | Tamanho do .PP em bytes |
| `restored_size` | int | Tamanho da imagem restaurada em bytes |
| `quality` | int | Qualidade usada na compressão |
| `time_seconds` | float | Tempo de descompressão |
| `pixels_per_second` | int | Throughput |

### `info(input_path) → dict`

Lê o header de um arquivo .PP sem descomprimir os dados. Operação instantânea.

**Parâmetros:**
- `input_path` (str): Caminho do arquivo .PP.

**Retorna:** Dicionário com metadados do arquivo.

**Exemplo:**

```python
from pied_piper import info

meta = info("foto.PP")
print(f"Imagem {meta['width']}x{meta['height']}")
print(f"Qualidade: {meta['quality']}")
print(f"Formato original: {meta['original_format']}")
```

**Campos retornados:**

| Campo | Tipo | Descrição |
|---|---|---|
| `file` | str | Caminho do arquivo |
| `file_size` | int | Tamanho em bytes |
| `version` | int | Versão do formato (2) |
| `header_size` | int | Bytes do header JSON |
| `data_size` | int | Bytes dos dados comprimidos |
| `width` | int | Largura |
| `height` | int | Altura |
| `total_pixels` | int | Pixels |
| `quality` | int | Qualidade usada |
| `has_alpha` | bool | Tem alpha |
| `original_format` | str | Formato original |
| `original_mode` | str | Modo original |

### `engine_info() → dict`

Retorna informações sobre o motor de compressão.

```python
from pied_piper.codec import engine_info

e = engine_info()
print(f"Motor: {e['engine']}")
print(f"C engine disponível: {e['c_engine_available']}")
print(f"Biblioteca: {e['library_path']}")
```

## 3. Exemplos Completos

### Exemplo 1: Compressão em lote

```python
import os
from pied_piper import compress

diretorio = "./fotos"
for nome in os.listdir(diretorio):
    if nome.lower().endswith(('.jpg', '.png', '.bmp')):
        entrada = os.path.join(diretorio, nome)
        try:
            stats = compress(entrada, quality=80)
            print(f"{nome}: {stats['reduction_percent']}% reducao")
        except Exception as e:
            print(f"{nome}: ERRO - {e}")
```

### Exemplo 2: Comparar qualidades

```python
from pied_piper import compress
import os

imagem = "teste.bmp"
original = os.path.getsize(imagem)

print(f"Original: {original} bytes\n")
print(f"{'Qualidade':<12}{'Tamanho':<15}{'Reducao':<12}{'Predicao':<12}")
print("-" * 55)

for q in [20, 40, 60, 80, 95]:
    stats = compress(imagem, f"teste_q{q}.PP", quality=q)
    print(f"{q:<12}{stats['compressed_size']:<15}"
          f"{stats['reduction_percent']}%{'':<5}"
          f"{stats['prediction_percent']}%")
```

### Exemplo 3: Roundtrip (compressão + descompressão + comparação)

```python
from pied_piper import compress, decompress
from PIL import Image
import numpy as np

# Comprime
stats_c = compress("original.png", "temp.PP", quality=75)
print(f"Comprimido: {stats_c['reduction_percent']}% menor")

# Descomprime
stats_d = decompress("temp.PP", "restaurada.png")
print(f"Tempo descompressao: {stats_d['time_seconds']}s")

# Calcula PSNR
orig = np.array(Image.open("original.png"))
rest = np.array(Image.open("restaurada.png"))
mse = ((orig.astype(float) - rest.astype(float)) ** 2).mean()
psnr = 20 * np.log10(255) - 10 * np.log10(mse)
print(f"PSNR: {psnr:.2f} dB")
```

### Exemplo 4: Inspecionar múltiplos arquivos .PP

```python
import os
from pied_piper import info

for f in os.listdir("."):
    if f.endswith(".PP"):
        meta = info(f)
        print(f"{f}: {meta['width']}x{meta['height']} "
              f"q={meta['quality']} "
              f"({meta['file_size']} bytes)")
```

## 4. Tratamento de Erros

As funções levantam as seguintes exceções:

- `FileNotFoundError` — arquivo de entrada não existe
- `ValueError` — arquivo .PP inválido, versão não suportada
- `RuntimeError` — motor C não carregado
- Exceções do Pillow — formato de imagem não suportado ou corrompido

```python
from pied_piper import compress

try:
    stats = compress("foto.jpg")
except FileNotFoundError:
    print("Arquivo nao encontrado")
except ValueError as e:
    print(f"Erro de formato: {e}")
except RuntimeError as e:
    print(f"Erro do motor: {e}")
```

## 5. Usando o Motor C Diretamente

Para casos avançados, é possível chamar diretamente o motor C via ctypes:

```python
from pied_piper.codec import _load_engine, MOStats
import ctypes

lib = _load_engine()
if lib:
    print("Motor C carregado")
    # Use lib.mo_compress_channel, lib.mo_decompress_channel, etc.
```

---

Para a interface de linha de comando, veja [USAGE.md](USAGE.md).
