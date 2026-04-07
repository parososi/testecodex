# Especificação do Formato .PP

Este documento define a estrutura binária dos arquivos `.PP` gerados pelo Pied Piper.

## 1. Estrutura Geral

```
┌──────────────────────────────────────────┐
│ Magic Number       (4 bytes)   "PPMO"    │  ← Pied Piper Middle-Out
├──────────────────────────────────────────┤
│ Versão do Formato  (2 bytes, u16 LE)     │  ← atual: 2
├──────────────────────────────────────────┤
│ Header Size        (4 bytes, u32 LE)     │
├──────────────────────────────────────────┤
│ Header JSON        (N bytes, UTF-8)      │
├──────────────────────────────────────────┤
│ Data Size          (4 bytes, u32 LE)     │
├──────────────────────────────────────────┤
│ Compressed Data    (M bytes, zlib)       │
└──────────────────────────────────────────┘
```

Todos os campos multi-byte são **little-endian**.

## 2. Magic Number

Os primeiros 4 bytes identificam o arquivo:

```
0x50 0x50 0x4D 0x4F    →    "PPMO"
                             (Pied Piper Middle-Out)
```

Se os 4 primeiros bytes não forem `PPMO`, o arquivo não é um .PP válido.

## 3. Versão

Campo `uint16` little-endian. A versão atual é **2**. Implementações devem rejeitar versões superiores às suportadas.

## 4. Header

O header é um objeto JSON serializado em UTF-8. O tamanho em bytes é declarado no campo `Header Size`.

### Campos obrigatórios

| Campo | Tipo | Descrição |
|---|---|---|
| `version` | int | Versão do formato (eco do campo binário) |
| `width` | int | Largura da imagem em pixels |
| `height` | int | Altura da imagem em pixels |
| `quality` | int | Qualidade usada na compressão (1-100) |
| `has_alpha` | bool | `true` se a imagem possui canal alpha |
| `original_format` | str | Formato original (ex: "PNG", "BMP") |
| `original_mode` | str | Modo de cor original (ex: "RGB", "RGBA", "L") |
| `cb_shape` | [int, int] | Dimensões do canal Cb após subamostragem |
| `cr_shape` | [int, int] | Dimensões do canal Cr após subamostragem |
| `y_size` | int | Tamanho em bytes do payload do canal Y |
| `cb_size` | int | Tamanho em bytes do payload do canal Cb |
| `cr_size` | int | Tamanho em bytes do payload do canal Cr |
| `alpha_size` | int | Tamanho em bytes do payload do canal Alpha (0 se `has_alpha=false`) |

### Exemplo de header

```json
{
  "version": 2,
  "width": 1024,
  "height": 1024,
  "quality": 75,
  "has_alpha": false,
  "original_format": "BMP",
  "original_mode": "RGB",
  "cb_shape": [512, 512],
  "cr_shape": [512, 512],
  "y_size": 180340,
  "cb_size": 43220,
  "cr_size": 43887,
  "alpha_size": 0
}
```

## 5. Data

O bloco de dados é **comprimido com zlib nível 9**. Após descompressão, ele contém a concatenação dos payloads de cada canal na seguinte ordem:

```
[ Y payload ] [ Cb payload ] [ Cr payload ] [ Alpha payload (opcional) ]
```

Os tamanhos de cada seção estão declarados no header (`y_size`, `cb_size`, `cr_size`, `alpha_size`).

## 6. Formato de um Payload de Canal

Cada payload de canal é gerado pelo motor C `mo_compress_channel()` e tem a estrutura:

```
┌──────────────────────────────────────────┐
│ Num Blocks          (4 bytes, u32 LE)    │
├──────────────────────────────────────────┤
│ Block[0]                                 │
│ Block[1]                                 │
│ ...                                      │
│ Block[N-1]                               │
└──────────────────────────────────────────┘
```

### Estrutura de um Block

```
┌──────────────────────────────────────────┐
│ Delta Flag         (1 byte, u8)          │  0=absoluto, 1=delta
├──────────────────────────────────────────┤
│ Adapt Factor Byte  (1 byte, u8)          │  fator adaptativo × 25.5
├──────────────────────────────────────────┤
│ RLE Size           (2 bytes, u16 LE)     │  tamanho do payload RLE
├──────────────────────────────────────────┤
│ RLE Payload        (RLE Size bytes)      │
└──────────────────────────────────────────┘
```

Os blocos estão ordenados na **sequência Middle-Out em espiral**, começando do bloco central e se expandindo para fora. A ordem exata é determinística dada a largura e altura do canal, e é reconstruída pelo decodificador via `mo_spiral_order()`.

## 7. Formato do RLE Payload

O RLE codifica coeficientes DCT quantizados em ordem zigzag (64 valores):

```
Formato: sequência de triplas (skip, value_lo, value_hi)

  skip      (1 byte)     : número de zeros antes do valor (0-254)
  value_lo  (1 byte)     : byte baixo do valor int16
  value_hi  (1 byte)     : byte alto do valor int16

Casos especiais:
  (0xFF, 0x00, 0x00)   : marcador de fim / flush de 255 zeros
```

**Exemplo:** A sequência `[5, 0, 0, 3, 0, 0, 0, 0, 0, -2, 0, 0, ...]` vira:

```
(0, 5, 0)       # valor 5 com 0 zeros antes
(2, 3, 0)       # valor 3 com 2 zeros antes
(5, -2, -1)     # valor -2 com 5 zeros antes (complemento de 2)
(0xFF, 0, 0)    # fim
```

## 8. Reconstrução

Para decodificar um arquivo .PP:

1. Ler magic number, validar `"PPMO"`
2. Ler versão, validar ≤ 2
3. Ler header size, ler e parsear header JSON
4. Ler data size, ler bloco comprimido
5. Descomprimir com zlib
6. Separar payloads Y / Cb / Cr / Alpha usando os tamanhos do header
7. Para cada canal:
   a. Gerar a ordem espiral Middle-Out (determinística)
   b. Para cada bloco: ler flag delta, fator adaptativo, RLE
   c. Decodificar RLE → zigzag inverso → dequantização → IDCT → se delta, somar ao bloco anterior
8. Upsampling 4:2:0 dos canais Cb e Cr
9. Combinar YCbCr → RGB
10. Se `has_alpha`, aplicar canal alpha decodificado
11. Retornar imagem final

## 9. Compatibilidade

| Versão do arquivo | Descrição |
|---|---|
| 1 (legado) | Formato inicial (JSON payload, DCT em Python puro) — **não compatível** |
| **2 (atual)** | Middle-Out Compression com motor C, zlib final |

A versão 2 é a única suportada pelo codec atual. Arquivos versão 1 devem ser re-comprimidos.

## 10. Exemplo de Bytes

Arquivo hipotético de 100 bytes:

```
Offset  Bytes                        Descrição
------  ---------------------------- ----------------------------------------
0x0000  50 50 4D 4F                  Magic "PPMO"
0x0004  02 00                        Version 2
0x0006  4C 00 00 00                  Header size = 76
0x000A  7B 22 76 65 72 73 69 6F ...  Header JSON ({"version":...)
0x0056  18 00 00 00                  Data size = 24
0x005A  78 9C ... (zlib stream)      Compressed data
```
