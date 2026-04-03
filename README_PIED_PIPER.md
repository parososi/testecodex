# Pied Piper - Compressor de Imagens .PP

> "Making the world a better place... through compression"

## O que e?

Pied Piper e o compressor de imagens mais eficiente da Internet. Ele utiliza um algoritmo proprietario que combina tecnicas avancadas de processamento de sinal para comprimir imagens em um formato proprietario `.PP`.

## Como funciona?

O algoritmo Pied Piper utiliza as seguintes tecnicas em cadeia:

1. **Conversao YCbCr** - Separa luminancia (brilho) de crominancia (cor), aproveitando a menor sensibilidade do olho humano a cores
2. **Subamostragem 4:2:0** - Reduz os canais de cor pela metade em cada dimensao (75% menos dados de cor)
3. **DCT 8x8** - Transformada Discreta de Cosseno em blocos 8x8 pixels
4. **Quantizacao Adaptativa** - Descarta informacao imperceptivel baseada no nivel de qualidade
5. **Codificacao RLE** - Run-Length Encoding para comprimir sequencias de zeros
6. **Compressao zlib** - Compressao final dos dados serializados

## Instalacao

```bash
pip install -r requirements.txt
```

## Uso

### Comprimir uma imagem
```bash
python -m pied_piper compress minha_foto.png -o minha_foto.PP -q 75
```

### Descomprimir um arquivo .PP
```bash
python -m pied_piper decompress minha_foto.PP -o minha_foto_restaurada.png
```

### Ver informacoes de um arquivo .PP
```bash
python -m pied_piper info minha_foto.PP
```

## Opcoes de qualidade

| Qualidade | Descricao | Uso recomendado |
|-----------|-----------|-----------------|
| 1-30 | Baixa | Thumbnails, previews |
| 31-60 | Media | Web, redes sociais |
| 61-80 | Alta | Uso geral (padrao: 75) |
| 81-100 | Maxima | Fotografia, impressao |

## Formatos suportados

**Entrada:** PNG, JPEG, BMP, TIFF, GIF, WebP, e qualquer formato suportado pelo Pillow

**Saida:** Formato proprietario `.PP` (compressao) ou qualquer formato de imagem (descompressao)

## Estrutura do arquivo .PP

```
[MAGIC 4B "PPCM"] [VERSION 2B] [HEADER_SIZE 4B] [HEADER JSON] [DADOS zlib]
```

## Exemplo de saida

```
============================================================
  PIED PIPER - ESTATISTICAS DE COMPRESSAO
============================================================
  Dimensoes:             512x512
  Total de pixels:       262,144
  Tamanho original:      768.05 KB
  Tamanho comprimido:    34.22 KB
  Taxa de compressao:    22.44:1
  Reducao:               95.54%
  [###############################################---]
============================================================
```
