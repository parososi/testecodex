/*
 * Pied Piper - Middle-Out Compression Engine
 * ===========================================
 * Motor de compressao de alta performance em C.
 *
 * O algoritmo Middle-Out processa blocos do centro da imagem para
 * as bordas, usando blocos centrais como referencia preditiva.
 * Isso explora a correlacao espacial natural das imagens onde o
 * centro tende a conter o "sujeito" principal.
 *
 * Pipeline:
 *   1. Haar Wavelet Decomposition (separacao multi-resolucao)
 *   2. Middle-Out block ordering (espiral do centro para fora)
 *   3. Fast DCT via matrix multiplication (O(N^2) por bloco)
 *   4. Delta prediction entre blocos adjacentes
 *   5. Adaptive quantization por complexidade local
 *   6. Zigzag + RLE + Delta encoding
 */

#ifndef MIDDLEOUT_H
#define MIDDLEOUT_H

#include <stdint.h>
#include <stddef.h>

/* Tamanho do bloco de processamento */
#define MO_BLOCK_SIZE 8

/* Resultado de operacao */
#define MO_OK          0
#define MO_ERR_NULL   -1
#define MO_ERR_SIZE   -2
#define MO_ERR_ALLOC  -3

/* Estrutura de um bloco quantizado */
typedef struct {
    int16_t data[64];  /* 8x8 coeficientes em ordem zigzag */
} MOBlock;

/* Estatisticas do processamento */
typedef struct {
    uint32_t total_blocks;
    uint32_t zero_blocks;       /* blocos totalmente zero (poupados) */
    uint32_t predicted_blocks;  /* blocos codificados por delta */
    double   avg_energy;        /* energia media dos blocos */
    double   sparsity;          /* porcentagem de zeros nos coeficientes */
} MOStats;

/* ===== Funcoes de transformada ===== */

/* DCT 2D rapida usando multiplicacao de matrizes pre-computadas */
void mo_dct8x8(const double *block_in, double *block_out);

/* IDCT 2D rapida */
void mo_idct8x8(const double *block_in, double *block_out);

/* ===== Haar Wavelet ===== */

/* Decomposicao wavelet 1 nivel em canal (in-place) */
void mo_haar_forward(double *channel, int width, int height);

/* Reconstrucao wavelet */
void mo_haar_inverse(double *channel, int width, int height);

/* ===== Middle-Out Ordering ===== */

/*
 * Gera ordem de processamento Middle-Out (espiral do centro).
 * Preenche arrays block_rows[] e block_cols[] com a sequencia.
 * Retorna numero total de blocos.
 */
int mo_spiral_order(int img_width, int img_height,
                    int *block_rows, int *block_cols,
                    int max_blocks);

/* ===== Quantizacao Adaptativa ===== */

/*
 * Calcula fator de quantizacao local baseado na variancia do bloco.
 * Blocos complexos (alta variancia) recebem quantizacao mais leve.
 * Blocos suaves (baixa variancia) recebem quantizacao mais agressiva.
 */
double mo_adaptive_quant_factor(const double *block, int size, int quality);

/* Quantiza um bloco DCT 8x8 com tabela e fator adaptativo */
void mo_quantize(const double *dct_block, int16_t *quant_out,
                 const double *quant_table, double adapt_factor);

/* Dequantiza */
void mo_dequantize(const int16_t *quant_in, double *dct_out,
                   const double *quant_table, double adapt_factor);

/* ===== Delta Prediction ===== */

/*
 * Codifica bloco como diferenca do bloco de referencia.
 * Se a predicao reduz energia, usa delta; senao, usa o bloco original.
 * Retorna 1 se usou predicao, 0 se nao.
 */
int mo_delta_encode(const int16_t *current, const int16_t *reference,
                    int16_t *output);

/* Decodifica delta */
void mo_delta_decode(const int16_t *delta, const int16_t *reference,
                     int16_t *output);

/* ===== Zigzag Scan ===== */

void mo_zigzag_forward(const int16_t matrix[8][8], int16_t linear[64]);
void mo_zigzag_inverse(const int16_t linear[64], int16_t matrix[8][8]);

/* ===== RLE Encoding ===== */

/*
 * RLE otimizado para coeficientes DCT (muitos zeros).
 * Formato: (skip_zeros, value) pairs.
 * Retorna numero de bytes escritos em output.
 */
int mo_rle_encode(const int16_t *data, int length,
                  uint8_t *output, int max_output);

/* Decodifica RLE. Retorna numero de valores decodificados. */
int mo_rle_decode(const uint8_t *input, int input_length,
                  int16_t *output, int max_output);

/* ===== Processamento completo de canal ===== */

/*
 * Processa um canal inteiro: Middle-Out ordering -> DCT -> Quant -> Delta -> Zigzag -> RLE
 * Retorna buffer alocado com dados comprimidos (caller deve free()).
 * compressed_size recebe o tamanho em bytes.
 */
uint8_t* mo_compress_channel(const double *channel, int width, int height,
                             const double *quant_table, int quality,
                             int *compressed_size, MOStats *stats);

/*
 * Reconstroi canal a partir dos dados comprimidos.
 * Retorna buffer alocado com canal reconstruido (caller deve free()).
 */
double* mo_decompress_channel(const uint8_t *compressed, int compressed_size,
                              int width, int height,
                              const double *quant_table, int quality);

#endif /* MIDDLEOUT_H */
