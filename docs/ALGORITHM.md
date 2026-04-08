# Algoritmo Middle-Out Compression — Documentacao Tecnica

Este documento descreve o algoritmo implementado no Pied Piper v3.0,
incluindo uma avaliacao honesta do que e original e o que usa tecnicas
estabelecidas, e a documentacao completa do novo modo lossless.

---

## 1. Visao Geral

O Pied Piper implementa **dois modos** de compressao, ambos usando a ordenacao
em espiral Middle-Out como inovacao central:

| Modo | Flag | Perda de dados | Algoritmo base |
|------|------|:--------------:|----------------|
| **Lossy** | (padrao) | Sim (ajustavel por qualidade) | DCT + Quantizacao adaptativa |
| **Lossless** | `-l` | **Nao** | DPCM + RCT reversivel |

A ordem em espiral do centro para as bordas e o elemento genuinamente original.

```
Espiral Middle-Out (blocos 8x8):

 Bloco 9  Bloco 2  Bloco 3  Bloco 4
 Bloco 8  CENTRO   →        Bloco 5
 Bloco 7  Bloco 6  ↓        ←
 ...

O primeiro bloco processado e o central.
Cada bloco seguinte e processado usando o anterior como referencia.
```

---

## 2. Modo Lossy — Pipeline DCT Middle-Out

### Estagio 1: Carregamento
Pillow carrega qualquer formato (PNG, JPEG, BMP, TIFF, GIF, WEBP, etc.)
e converte para RGB uint8 ou RGBA uint8.

### Estagio 2: Conversao de Cor RGB -> YCbCr
Separa luminancia (Y) de crominancia (Cb, Cr):
```
Y  =  0.299 R + 0.587 G + 0.114 B
Cb = -0.169 R - 0.331 G + 0.500 B + 128
Cr =  0.500 R - 0.419 G - 0.081 B + 128
```
O olho humano e mais sensivel a variacao de Y do que de Cb/Cr.

### Estagio 3: Subamostragem 4:2:0
Reduz Cb e Cr para metade da resolucao em cada eixo.
**Nota:** Este estagio e identico ao JPEG e e lossy.

### Estagio 4: Ordenacao em Espiral Middle-Out
```c
// Gera a ordem dos blocos 8x8 comecando do centro
int n = mo_spiral_order(width, height, spiral_r, spiral_c, max_blocks);
```
A espiral começa no bloco central e se expande para direita, baixo,
esquerda, cima — padrão de expansão quadrangular.

### Estagio 5: DCT 8x8 por Bloco
DCT-II bidimensional via multiplicacao de matrizes pre-computadas:
```
DCT(bloco) = D * bloco * D^T
```
Concentra energia em coeficientes de baixa frequencia.

### Estagio 6: Quantizacao Adaptativa
**Diferente do JPEG:** O fator de quantizacao e ajustado por variancia local:
```c
double adapt = mo_adaptive_quant_factor(block, 64, quality);
// Blocos complexos (alta variancia) -> quantizacao mais leve
// Blocos suaves (baixa variancia)   -> quantizacao mais agressiva
```
Isso preserva detalhes onde o olho humano nota mais.

### Estagio 7: Delta Prediction + RLE + zlib
Para cada bloco na ordem espiral, calcula se e mais eficiente armazenar
o bloco diretamente ou como diferenca do bloco anterior:
```
energia_delta < energia_raw * 90% -> usa delta
```
Os coeficientes quantizados passam por zigzag scan + RLE + zlib.

---

## 3. Modo Lossless — Middle-Out DPCM + RCT

### Inovacao: DPCM na Ordem Espiral

Diferente do PNG (predicao horizontal por scanline) e do JPEG-LS
(predicao pixel a pixel com contexto adaptativo), o modo lossless do
Pied Piper usa **predicao entre blocos 8x8 na ordem espiral Middle-Out**.

Hipotese: em imagens naturais, a correlacao entre blocos decresce
conforme a distancia do centro. Processar em espiral maximiza a
correlacao entre blocos consecutivos.

### Pipeline Lossless

```
Imagem RGB (uint8)
       |
       v
[1] RCT - Transformada de Cor Reversivel (JPEG 2000 padrao)
       Y  = G
       Co = R - B
       Cg = G - floor((R + B) / 2)
       |
       v (todos int16, sem arredondamento, sem perdas)
       |
[2] Para cada canal (Y, Co, Cg):
       |
       v
[3] Gera espiral Middle-Out dos blocos 8x8
       |
       v
[4] Para cada bloco na espiral:
       - Extrai 8x8 valores int16
       - Calcula residuais do bloco anterior (DPCM)
       - Se energia_delta < 90% da energia_raw: usa delta
       - Senao: armazena bloco raw
       |
       v
[5] RLE dos residuais int16 (faixa -255..255)
       |
       v
[6] Concatena todos os canais
       |
       v
[7] zlib nivel 9
       |
       v
[8] Salva arquivo .PP com header JSON
    (inclui hash SHA-256 do original para verificacao)
```

### Garantia de Lossless

A reconstrucao e exata porque:
1. RCT e invertivel em aritmetica inteira (sem arredondamento acumulado)
2. DPCM e invertivel: bloco = residual + bloco_anterior
3. RLE e invertivel
4. zlib e invertivel

A verificacao SHA-256 confirma que os pixels reconstruidos sao bit-a-bit
identicos aos originais:

```bash
pp c foto.png -l       # Comprime (grava hash no .PP)
pp d foto.PP           # Descomprime (compara hash, exibe VERIFICADA)
pp verify foto.png     # Pipeline completo de verificacao automatica
```

---

## 4. Avaliacao de Originalidade

| Componente | Tecnica | Originalidade |
|---|---|---|
| Espiral do centro para bordas | Original | Nao documentada em codec padrão |
| DPCM entre blocos na espiral | Original | Distinto de PNG e JPEG-LS |
| DCT 8x8 | JPEG (1974) | Tecnica estabelecida |
| Quantizacao adaptativa por variancia | Parcial (HEVC usa algo similar) | Implementacao propria |
| Subamostragem 4:2:0 | JPEG padrao | Nenhuma |
| RCT (Y, Co, Cg) | JPEG 2000 padrao | Nenhuma |
| RLE de coeficientes | JPEG padrao | Nenhuma |
| zlib | Padrao universal | Nenhuma |
| SHA-256 para verificacao | Padrao de segurança | Aplicacao ao contexto |

**Resumo:** O elemento central original e a **espiral Middle-Out para
predicao DPCM**. O restante combina tecnicas estabelecidas de forma
eficiente. A originalidade esta na composicao e na aplicacao da ordenacao
espiral para predicao entre blocos.

---

## 5. Comparacao com Formatos Existentes

| Formato | Tipo | Predicao | Ordenacao |
|---|---|---|---|
| PNG | Lossless | Pixel (Paeth filter) | Scanline esquerda->direita |
| JPEG | Lossy | Delta entre blocos DC | Raster esquerda->direita |
| JPEG-LS | Lossless | Pixel (LOCO-I adaptativo) | Scanline esquerda->direita |
| JPEG 2000 | Lossy/Lossless | Wavelet multinivel | Particionamento em tiles |
| HEVC | Lossy | Intra prediction 35 modos | Raster com quad-tree |
| **PP (Lossy)** | **Lossy** | **Delta bloco->bloco** | **Espiral Middle-Out** |
| **PP (Lossless)** | **Lossless** | **DPCM bloco->bloco** | **Espiral Middle-Out** |

A ordenacao em espiral e a principal diferenca arquitetural do Pied Piper.

---

## 6. Complexidade Computacional

| Operacao | Complexidade |
|---|---|
| Geracao da espiral | O(n_blocos) |
| DCT 8x8 por bloco | O(n^2) com pre-computacao = 128 mul + 128 add |
| DPCM lossless | O(64) por bloco = 64 sub |
| RLE | O(64) por bloco |
| zlib | O(dados) |
| **Total** | **O(W * H)** linear nos pixels |

Throughput medido: ~1.36 M pixels/segundo com motor C (gcc -O3).

---

## 7. Formato do Arquivo .PP (v3)

```
[4 bytes] Magic: "PPMO" (Pied Piper Middle-Out)
[2 bytes] Version: 3 (uint16 LE)
[4 bytes] Header size (uint32 LE)
[N bytes] Header JSON UTF-8:
    {
      "version": 3,
      "lossless": true/false,
      "width": 1024,
      "height": 1024,
      "quality": 75,          // ou 100 se lossless
      "has_alpha": false,
      "original_format": "PNG",
      "original_mode": "RGB",
      "original_hash": "sha256...",  // apenas se lossless
      // Lossy:
      "cb_shape": [512, 512],
      "cr_shape": [512, 512],
      "y_size": N, "cb_size": N, "cr_size": N, "alpha_size": 0
      // Lossless:
      "y_size": N, "co_size": N, "cg_size": N, "alpha_size": 0
    }
[4 bytes] Data size (uint32 LE)
[M bytes] zlib-compressed channel data
```

Backward compatibility: arquivos .PP v2 (lossy) sao lidos corretamente pelo
codec v3.
