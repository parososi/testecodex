# Guia de Uso do Pied Piper

Guia completo para usar o compressor Pied Piper via linha de comando.

## 1. Instalação

### Pré-requisitos

- Python 3.8 ou superior
- GCC (para compilar o motor C)
- Pillow e NumPy

### Passos

```bash
# 1. Clone o repositório
git clone https://github.com/parososi/testecodex.git
cd testecodex

# 2. Instale as dependências Python
pip install -r requirements.txt

# 3. Torne o executável acessível (opcional)
chmod +x pp
```

O motor C (`libmiddleout.so`) é compilado **automaticamente** na primeira execução do comando `./pp`. Para compilar manualmente:

```bash
cd engine
make
```

## 2. Comandos Básicos

O Pied Piper tem apenas 3 comandos principais, todos com aliases curtos:

| Comando curto | Alias | Descrição |
|---|---|---|
| `pp c` | `pp compress` | Comprimir imagem para .PP |
| `pp d` | `pp decompress`, `pp x` | Descomprimir .PP para imagem |
| `pp i` | `pp info` | Mostrar informações de um .PP |

Comandos auxiliares:

| Comando | Descrição |
|---|---|
| `pp help` | Exibir ajuda completa |
| `pp version` | Mostrar versão |
| `pp engine` | Status do motor de compressão |

## 3. Comprimir Imagens

### Sintaxe

```
pp c <arquivo_entrada> [-q QUALIDADE] [-o ARQUIVO_SAIDA]
```

### Exemplos

```bash
# Compressão básica (qualidade padrão 75)
pp c foto.jpg
# → foto.PP

# Qualidade alta
pp c foto.png -q 90

# Qualidade baixa (máxima compressão)
pp c foto.bmp -q 30

# Saída customizada
pp c foto.tiff -o comprimida.PP

# Qualidade + saída customizada
pp c imagem.webp -q 85 -o saida.PP
```

### Níveis de Qualidade

| Faixa | Descrição | Uso Recomendado |
|---|---|---|
| 1–30 | Máxima compressão | Thumbnails, previews |
| 31–60 | Balanceado | Redes sociais, web |
| 61–80 | Alta qualidade (padrão: 75) | Uso geral |
| 81–100 | Quase sem perdas | Fotografia, impressão |

### Estatísticas Reportadas

Após a compressão, você verá:

- **Tamanho original e comprimido** em KB/MB
- **Taxa de compressão** (ex: 11.41:1)
- **Redução percentual** com barra visual
- **Bits por pixel**
- **Blocos processados** pelo motor Middle-Out
- **Blocos preditos** (usaram delta encoding)
- **Blocos vazios** (totalmente zerados)
- **Esparsidade DCT** (% de coeficientes zerados)
- **Tempo** e **throughput** em pixels/segundo

## 4. Descomprimir Arquivos .PP

### Sintaxe

```
pp d <arquivo.PP> [-o ARQUIVO_SAIDA]
```

### Exemplos

```bash
# Descompressão básica (gera PNG)
pp d foto.PP
# → foto_restored.png

# Saída customizada
pp d foto.PP -o restaurada.png

# Saída em outro formato (detectado pela extensão)
pp d foto.PP -o restaurada.jpg
pp d foto.PP -o restaurada.bmp
pp d foto.PP -o restaurada.tiff
```

O formato de saída é detectado automaticamente pela extensão do arquivo. Qualquer formato suportado pelo Pillow pode ser usado.

## 5. Inspecionar Arquivos .PP

### Sintaxe

```
pp i <arquivo.PP>
```

### Exemplo

```bash
pp i foto.PP
```

Saída:

```
================================================================
              PIED PIPER - INFO DO ARQUIVO .PP
================================================================
  Arquivo:              foto.PP
  Tamanho total:        269.21 KB
  Versao do formato:    2
  Header:               222.00 B
  Dados comprimidos:    268.97 KB
----------------------------------------------------------------
  Dimensoes:            1024 x 1024
  Total pixels:         1,048,576
  Qualidade:            75/100
  Canal Alpha:          Nao
  Formato original:     BMP (RGB)
================================================================
```

Este comando **não descomprime** a imagem — apenas lê o header, sendo instantâneo.

## 6. Status do Motor

```bash
pp engine
```

Mostra se o motor C está compilado e carregado:

```
================================================================
           PIED PIPER - MOTOR DE COMPRESSAO
================================================================
  Motor:                C (libmiddleout)
  C engine disponivel:  Sim
  Biblioteca:           /home/user/testecodex/engine/libmiddleout.so
  Versao Python:        2.0.0
================================================================
```

## 7. Formatos de Imagem Suportados

O Pied Piper aceita **praticamente todos os formatos de imagem existentes** como entrada, via Pillow:

**Formatos comuns:**
- PNG (com e sem alpha)
- JPEG / JPG
- BMP
- TIFF / TIF
- GIF (primeiro frame)
- WebP
- ICO

**Formatos especializados:**
- TGA (Targa)
- PCX
- PPM / PGM / PBM / PNM
- PSD (Photoshop)
- DDS (DirectDraw Surface)
- APNG (Animated PNG, primeiro frame)
- JP2 / JPX (JPEG 2000)
- SGI
- XBM / XPM
- DIB
- EPS
- PALM
- WMF / EMF
- e muitos outros

Para **descompressão**, qualquer formato suportado pelo Pillow pode ser usado como saída.

## 8. Workflow Completo

Exemplo de ciclo completo:

```bash
# 1. Ver ajuda
./pp help

# 2. Verificar motor
./pp engine

# 3. Comprimir uma foto
./pp c minha_foto.jpg -q 80

# 4. Ver informações do arquivo gerado
./pp i minha_foto.PP

# 5. Descomprimir de volta
./pp d minha_foto.PP -o minha_foto_restaurada.png

# 6. Verificar se funcionou
ls -la minha_foto*
```

## 9. Dicas e Truques

### Compressão em lote (bash)

```bash
# Comprimir todas as imagens de um diretório
for img in *.jpg; do
    ./pp c "$img" -q 80
done

# Descomprimir todos os .PP
for pp in *.PP; do
    ./pp d "$pp"
done
```

### Comparar tamanhos

```bash
./pp c foto.jpg
ls -lh foto.jpg foto.PP
```

### Testar diferentes qualidades

```bash
for q in 30 50 70 90; do
    ./pp c foto.jpg -q $q -o foto_q$q.PP
    echo "Quality $q: $(ls -l foto_q$q.PP | awk '{print $5}') bytes"
done
```

## 10. Troubleshooting

### "Motor C nao encontrado"

O motor C não foi compilado. Execute:

```bash
cd engine
make
```

### "gcc: command not found"

Instale o compilador C:

```bash
# Ubuntu/Debian
sudo apt install build-essential

# macOS
xcode-select --install

# Fedora
sudo dnf install gcc make
```

### "ModuleNotFoundError: No module named 'PIL'"

Instale as dependências Python:

```bash
pip install -r requirements.txt
```

### Arquivo .PP fica maior que o original

Isso acontece quando a imagem de entrada já está fortemente comprimida (ex: JPEG de alta compressão, WebP, JPEG2000). Para essas imagens, o ganho do Pied Piper é limitado porque elas já eliminaram a redundância. O Pied Piper brilha em **imagens não-comprimidas** (BMP, TIFF, PNG) ou **screenshots**, onde atinge reduções de 85-95%.

---

Para detalhes do algoritmo, veja [ALGORITHM.md](ALGORITHM.md). Para integração programática, veja [API.md](API.md).
