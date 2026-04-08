/*
 * Pied Piper - Middle-Out Compression Engine
 * Implementacao do motor de compressao em C puro.
 */

#include "middleout.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

/* ===== Tabela DCT pre-computada ===== */

static double DCT_MATRIX[8][8];
static double DCT_MATRIX_T[8][8];
static int dct_initialized = 0;

static void init_dct_matrix(void) {
    if (dct_initialized) return;
    int i, j;
    for (i = 0; i < 8; i++) {
        for (j = 0; j < 8; j++) {
            if (i == 0) {
                DCT_MATRIX[i][j] = 1.0 / sqrt(8.0);
            } else {
                DCT_MATRIX[i][j] = sqrt(2.0 / 8.0) *
                    cos((2.0 * j + 1.0) * i * M_PI / 16.0);
            }
            DCT_MATRIX_T[j][i] = DCT_MATRIX[i][j];
        }
    }
    dct_initialized = 1;
}

/* Multiplicacao de matrizes 8x8: C = A * B */
static void mat_mul_8x8(const double A[8][8], const double B[8][8],
                         double C[8][8]) {
    int i, j, k;
    for (i = 0; i < 8; i++) {
        for (j = 0; j < 8; j++) {
            double sum = 0.0;
            for (k = 0; k < 8; k++) {
                sum += A[i][k] * B[k][j];
            }
            C[i][j] = sum;
        }
    }
}

/* ===== DCT 2D via multiplicacao de matrizes ===== */
/* DCT(block) = DCT_MATRIX * block * DCT_MATRIX^T */

void mo_dct8x8(const double *block_in, double *block_out) {
    init_dct_matrix();
    double in_mat[8][8], temp[8][8], out_mat[8][8];
    int i, j;

    for (i = 0; i < 8; i++)
        for (j = 0; j < 8; j++)
            in_mat[i][j] = block_in[i * 8 + j];

    mat_mul_8x8(DCT_MATRIX, in_mat, temp);
    mat_mul_8x8(temp, DCT_MATRIX_T, out_mat);

    for (i = 0; i < 8; i++)
        for (j = 0; j < 8; j++)
            block_out[i * 8 + j] = out_mat[i][j];
}

void mo_idct8x8(const double *block_in, double *block_out) {
    init_dct_matrix();
    double in_mat[8][8], temp[8][8], out_mat[8][8];
    int i, j;

    for (i = 0; i < 8; i++)
        for (j = 0; j < 8; j++)
            in_mat[i][j] = block_in[i * 8 + j];

    mat_mul_8x8(DCT_MATRIX_T, in_mat, temp);
    mat_mul_8x8(temp, DCT_MATRIX, out_mat);

    for (i = 0; i < 8; i++)
        for (j = 0; j < 8; j++)
            block_out[i * 8 + j] = out_mat[i][j];
}

/* ===== Haar Wavelet ===== */

void mo_haar_forward(double *channel, int width, int height) {
    int i, j;
    double *temp = (double *)malloc(sizeof(double) * (width > height ? width : height));
    if (!temp) return;

    /* Transformada nas linhas */
    for (i = 0; i < height; i++) {
        int half = width / 2;
        for (j = 0; j < half; j++) {
            double a = channel[i * width + 2 * j];
            double b = channel[i * width + 2 * j + 1];
            temp[j]        = (a + b) / sqrt(2.0);      /* Aproximacao */
            temp[half + j]  = (a - b) / sqrt(2.0);      /* Detalhe */
        }
        for (j = 0; j < width; j++)
            channel[i * width + j] = temp[j];
    }

    /* Transformada nas colunas */
    for (j = 0; j < width; j++) {
        int half = height / 2;
        for (i = 0; i < half; i++) {
            double a = channel[(2 * i) * width + j];
            double b = channel[(2 * i + 1) * width + j];
            temp[i]        = (a + b) / sqrt(2.0);
            temp[half + i]  = (a - b) / sqrt(2.0);
        }
        for (i = 0; i < height; i++)
            channel[i * width + j] = temp[i];
    }

    free(temp);
}

void mo_haar_inverse(double *channel, int width, int height) {
    int i, j;
    double *temp = (double *)malloc(sizeof(double) * (width > height ? width : height));
    if (!temp) return;

    /* Inversa nas colunas */
    for (j = 0; j < width; j++) {
        int half = height / 2;
        for (i = 0; i < half; i++) {
            double a = channel[i * width + j];
            double d = channel[(half + i) * width + j];
            temp[2 * i]     = (a + d) / sqrt(2.0);
            temp[2 * i + 1] = (a - d) / sqrt(2.0);
        }
        for (i = 0; i < height; i++)
            channel[i * width + j] = temp[i];
    }

    /* Inversa nas linhas */
    for (i = 0; i < height; i++) {
        int half = width / 2;
        for (j = 0; j < half; j++) {
            double a = channel[i * width + j];
            double d = channel[i * width + half + j];
            temp[2 * j]     = (a + d) / sqrt(2.0);
            temp[2 * j + 1] = (a - d) / sqrt(2.0);
        }
        for (j = 0; j < width; j++)
            channel[i * width + j] = temp[j];
    }

    free(temp);
}

/* ===== Middle-Out Spiral Order ===== */

int mo_spiral_order(int img_width, int img_height,
                    int *block_rows, int *block_cols,
                    int max_blocks) {
    int bw = (img_width + MO_BLOCK_SIZE - 1) / MO_BLOCK_SIZE;
    int bh = (img_height + MO_BLOCK_SIZE - 1) / MO_BLOCK_SIZE;
    int total = bw * bh;
    if (total > max_blocks) total = max_blocks;

    /* Marca blocos visitados */
    uint8_t *visited = (uint8_t *)calloc(bw * bh, 1);
    if (!visited) return 0;

    /* Comeca do centro */
    int center_r = bh / 2;
    int center_c = bw / 2;

    /* Direcoes: direita, baixo, esquerda, cima */
    int dr[] = {0, 1, 0, -1};
    int dc[] = {1, 0, -1, 0};

    int count = 0;
    int r = center_r, c = center_c;
    int dir = 0;
    int steps = 1, step_count = 0, turns = 0;

    /* Primeiro bloco: centro */
    if (r >= 0 && r < bh && c >= 0 && c < bw) {
        block_rows[count] = r;
        block_cols[count] = c;
        visited[r * bw + c] = 1;
        count++;
    }

    /* Espiral para fora */
    while (count < total) {
        r += dr[dir];
        c += dc[dir];
        step_count++;

        if (r >= 0 && r < bh && c >= 0 && c < bw && !visited[r * bw + c]) {
            block_rows[count] = r;
            block_cols[count] = c;
            visited[r * bw + c] = 1;
            count++;
        }

        if (step_count >= steps) {
            step_count = 0;
            dir = (dir + 1) % 4;
            turns++;
            if (turns % 2 == 0)
                steps++;
        }

        /* Seguranca: se estiver fora dos limites por muito tempo, varrer restantes */
        if (r < -bh || r >= 2 * bh || c < -bw || c >= 2 * bw) {
            int i, j;
            for (i = 0; i < bh && count < total; i++) {
                for (j = 0; j < bw && count < total; j++) {
                    if (!visited[i * bw + j]) {
                        block_rows[count] = i;
                        block_cols[count] = j;
                        visited[i * bw + j] = 1;
                        count++;
                    }
                }
            }
            break;
        }
    }

    free(visited);
    return count;
}

/* ===== Quantizacao Adaptativa ===== */

double mo_adaptive_quant_factor(const double *block, int size, int quality) {
    /* Calcula variancia do bloco */
    double sum = 0.0, sum_sq = 0.0;
    int i;
    for (i = 0; i < size; i++) {
        sum += block[i];
        sum_sq += block[i] * block[i];
    }
    double mean = sum / size;
    double variance = (sum_sq / size) - (mean * mean);
    if (variance < 0) variance = 0;

    /*
     * Fator adaptativo:
     * - Alta variancia (textura complexa) -> fator menor (quantizacao mais leve)
     * - Baixa variancia (area suave) -> fator maior (quantizacao mais forte)
     * Isso preserva detalhes onde o olho nota e comprime mais onde nao nota.
     */
    double norm_var = variance / (255.0 * 255.0);
    double factor = 1.0 - 0.5 * (norm_var / (norm_var + 0.01));

    /* Escala pela qualidade */
    double q_scale;
    if (quality < 50)
        q_scale = 5000.0 / quality;
    else
        q_scale = 200.0 - 2.0 * quality;
    q_scale /= 100.0;

    return factor * q_scale;
}

void mo_quantize(const double *dct_block, int16_t *quant_out,
                 const double *quant_table, double adapt_factor) {
    int i;
    for (i = 0; i < 64; i++) {
        double q = quant_table[i] * adapt_factor;
        if (q < 1.0) q = 1.0;
        quant_out[i] = (int16_t)round(dct_block[i] / q);
    }
}

void mo_dequantize(const int16_t *quant_in, double *dct_out,
                   const double *quant_table, double adapt_factor) {
    int i;
    for (i = 0; i < 64; i++) {
        double q = quant_table[i] * adapt_factor;
        if (q < 1.0) q = 1.0;
        dct_out[i] = quant_in[i] * q;
    }
}

/* ===== Delta Prediction ===== */

int mo_delta_encode(const int16_t *current, const int16_t *reference,
                    int16_t *output) {
    if (!reference) {
        memcpy(output, current, 64 * sizeof(int16_t));
        return 0;
    }

    /* Calcula energia do original e do delta */
    long energy_orig = 0, energy_delta = 0;
    int16_t delta[64];
    int i;

    for (i = 0; i < 64; i++) {
        delta[i] = current[i] - reference[i];
        energy_orig += (long)current[i] * current[i];
        energy_delta += (long)delta[i] * delta[i];
    }

    /* Usa delta apenas se reduz energia em pelo menos 20% */
    if (energy_delta < energy_orig * 8 / 10) {
        memcpy(output, delta, 64 * sizeof(int16_t));
        return 1;
    } else {
        memcpy(output, current, 64 * sizeof(int16_t));
        return 0;
    }
}

void mo_delta_decode(const int16_t *delta, const int16_t *reference,
                     int16_t *output) {
    int i;
    for (i = 0; i < 64; i++) {
        output[i] = delta[i] + reference[i];
    }
}

/* ===== Zigzag Scan ===== */

static const int ZIGZAG_ORDER[64][2] = {
    {0,0},{0,1},{1,0},{2,0},{1,1},{0,2},{0,3},{1,2},
    {2,1},{3,0},{4,0},{3,1},{2,2},{1,3},{0,4},{0,5},
    {1,4},{2,3},{3,2},{4,1},{5,0},{6,0},{5,1},{4,2},
    {3,3},{2,4},{1,5},{0,6},{0,7},{1,6},{2,5},{3,4},
    {4,3},{5,2},{6,1},{7,0},{7,1},{6,2},{5,3},{4,4},
    {3,5},{2,6},{1,7},{2,7},{3,6},{4,5},{5,4},{6,3},
    {7,2},{7,3},{6,4},{5,5},{4,6},{3,7},{4,7},{5,6},
    {6,5},{7,4},{7,5},{6,6},{5,7},{6,7},{7,6},{7,7}
};

void mo_zigzag_forward(const int16_t matrix[8][8], int16_t linear[64]) {
    int i;
    for (i = 0; i < 64; i++)
        linear[i] = matrix[ZIGZAG_ORDER[i][0]][ZIGZAG_ORDER[i][1]];
}

void mo_zigzag_inverse(const int16_t linear[64], int16_t matrix[8][8]) {
    int i;
    for (i = 0; i < 64; i++)
        matrix[ZIGZAG_ORDER[i][0]][ZIGZAG_ORDER[i][1]] = linear[i];
}

/* ===== RLE Encoding ===== */
/*
 * Formato: pares de (skip, value) onde:
 *   - skip = numero de zeros antes do valor (1 byte, 0-255)
 *   - value = coeficiente (2 bytes, little-endian int16)
 *   - Marcador de fim: (0xFF, 0x00, 0x00)
 */

int mo_rle_encode(const int16_t *data, int length,
                  uint8_t *output, int max_output) {
    int pos = 0;
    int zeros = 0;
    int i;

    for (i = 0; i < length; i++) {
        if (data[i] == 0) {
            zeros++;
            if (zeros == 255) {
                /* Flush zeros como par (255, 0) */
                if (pos + 3 > max_output) break;
                output[pos++] = 255;
                output[pos++] = 0;
                output[pos++] = 0;
                zeros = 0;
            }
        } else {
            if (pos + 3 > max_output) break;
            output[pos++] = (uint8_t)zeros;
            output[pos++] = (uint8_t)(data[i] & 0xFF);
            output[pos++] = (uint8_t)((data[i] >> 8) & 0xFF);
            zeros = 0;
        }
    }

    /* Marcador de fim */
    if (pos + 3 <= max_output) {
        output[pos++] = 0xFF;
        output[pos++] = 0x00;
        output[pos++] = 0x00;
    }

    return pos;
}

int mo_rle_decode(const uint8_t *input, int input_length,
                  int16_t *output, int max_output) {
    int in_pos = 0, out_pos = 0;

    while (in_pos + 2 < input_length && out_pos < max_output) {
        uint8_t skip = input[in_pos];
        int16_t value = (int16_t)(input[in_pos + 1] | (input[in_pos + 2] << 8));
        in_pos += 3;

        /* Marcador de fim */
        if (skip == 0xFF && value == 0)
            break;

        /* Preenche zeros */
        int z;
        for (z = 0; z < skip && out_pos < max_output; z++)
            output[out_pos++] = 0;

        /* Valor (skip=255 value=0 e um flush de zeros, nao um valor) */
        if (!(skip == 255 && value == 0)) {
            if (out_pos < max_output)
                output[out_pos++] = value;
        }
    }

    /* Preenche restante com zeros */
    while (out_pos < max_output)
        output[out_pos++] = 0;

    return out_pos;
}

/* ===== Compressao Lossless Middle-Out DPCM ===== */

/*
 * mo_compress_lossless_ch:
 *   Comprime um canal usando DPCM entre blocos consecutivos na ordem Middle-Out.
 *   100% lossless: armazena residuais exatos sem quantizacao.
 *
 * Formato de saida:
 *   [4 bytes: n_blocks LE]
 *   [2 bytes: pw LE] [2 bytes: ph LE]
 *   Para cada bloco:
 *     [1 byte: used_delta]
 *     [2 bytes: rle_size LE]
 *     [rle_size bytes: dados RLE dos residuais int16]
 */
uint8_t* mo_compress_lossless_ch(const int16_t *channel, int width, int height,
                                  int *out_size, MOStats *stats) {
    int bw = (width  + MO_BLOCK_SIZE - 1) / MO_BLOCK_SIZE;
    int bh = (height + MO_BLOCK_SIZE - 1) / MO_BLOCK_SIZE;
    int total_blocks = bw * bh;
    int pw = bw * MO_BLOCK_SIZE;
    int ph = bh * MO_BLOCK_SIZE;

    /* Padding com borda replicada */
    int16_t *padded = (int16_t *)calloc(pw * ph, sizeof(int16_t));
    if (!padded) { *out_size = 0; return NULL; }

    int i, j;
    for (i = 0; i < height; i++) {
        for (j = 0; j < width; j++)
            padded[i * pw + j] = channel[i * width + j];
        for (j = width; j < pw; j++)
            padded[i * pw + j] = channel[i * width + (width - 1)];
    }
    for (i = height; i < ph; i++)
        memcpy(&padded[i * pw], &padded[(height - 1) * pw], pw * sizeof(int16_t));

    /* Gera ordem Middle-Out */
    int *spiral_r = (int *)malloc(total_blocks * sizeof(int));
    int *spiral_c = (int *)malloc(total_blocks * sizeof(int));
    if (!spiral_r || !spiral_c) {
        free(padded); free(spiral_r); free(spiral_c);
        *out_size = 0; return NULL;
    }
    int n_blocks = mo_spiral_order(pw, ph, spiral_r, spiral_c, total_blocks);

    /* Buffer de saida: header(8) + por bloco: flag(1)+rle_size(2)+rle(max ~195) */
    int max_out = 8 + n_blocks * 200;
    uint8_t *output = (uint8_t *)malloc(max_out);
    if (!output) {
        free(padded); free(spiral_r); free(spiral_c);
        *out_size = 0; return NULL;
    }

    int out_pos = 0;

    /* Header */
    output[out_pos++] = (uint8_t)(n_blocks        & 0xFF);
    output[out_pos++] = (uint8_t)((n_blocks >>  8) & 0xFF);
    output[out_pos++] = (uint8_t)((n_blocks >> 16) & 0xFF);
    output[out_pos++] = (uint8_t)((n_blocks >> 24) & 0xFF);
    output[out_pos++] = (uint8_t)(pw & 0xFF);
    output[out_pos++] = (uint8_t)((pw >> 8) & 0xFF);
    output[out_pos++] = (uint8_t)(ph & 0xFF);
    output[out_pos++] = (uint8_t)((ph >> 8) & 0xFF);

    if (stats) {
        memset(stats, 0, sizeof(MOStats));
        stats->total_blocks = n_blocks;
    }

    int16_t prev_block[64];
    int has_prev = 0;
    long total_res = 0, zero_res = 0;

    for (int b = 0; b < n_blocks; b++) {
        int br = spiral_r[b];
        int bc = spiral_c[b];
        int py = br * MO_BLOCK_SIZE;
        int px = bc * MO_BLOCK_SIZE;

        /* Extrai bloco atual */
        int16_t curr[64];
        for (i = 0; i < MO_BLOCK_SIZE; i++)
            for (j = 0; j < MO_BLOCK_SIZE; j++)
                curr[i * MO_BLOCK_SIZE + j] = padded[(py + i) * pw + (px + j)];

        /* DPCM: escolhe entre raw e delta */
        int16_t residuals[64];
        int used_delta = 0;

        if (has_prev) {
            long e_raw = 0, e_delta = 0;
            for (int k = 0; k < 64; k++) {
                int16_t d = curr[k] - prev_block[k];
                e_raw   += (long)curr[k] * curr[k];
                e_delta += (long)d * d;
                residuals[k] = d;
            }
            /* Usa delta se reduz energia em pelo menos 10% */
            if (e_delta <= e_raw * 9 / 10) {
                used_delta = 1;
            } else {
                memcpy(residuals, curr, 64 * sizeof(int16_t));
            }
        } else {
            memcpy(residuals, curr, 64 * sizeof(int16_t));
        }

        /* Estatisticas */
        for (int k = 0; k < 64; k++) {
            total_res++;
            if (residuals[k] == 0) zero_res++;
        }

        /* Escreve flag + RLE */
        output[out_pos++] = (uint8_t)used_delta;

        int rle_size = mo_rle_encode(residuals, 64,
                                     &output[out_pos + 2],
                                     max_out - out_pos - 2);
        output[out_pos++] = (uint8_t)(rle_size & 0xFF);
        output[out_pos++] = (uint8_t)((rle_size >> 8) & 0xFF);
        out_pos += rle_size;

        if (stats && used_delta) stats->predicted_blocks++;

        memcpy(prev_block, curr, 64 * sizeof(int16_t));
        has_prev = 1;
    }

    if (stats && n_blocks > 0)
        stats->sparsity = total_res > 0
            ? (double)zero_res / total_res * 100.0 : 0.0;

    *out_size = out_pos;
    free(padded);
    free(spiral_r);
    free(spiral_c);

    uint8_t *shrunk = (uint8_t *)realloc(output, out_pos);
    return shrunk ? shrunk : output;
}

/*
 * mo_decompress_lossless_ch:
 *   Descomprime canal produzido por mo_compress_lossless_ch.
 *   Retorna buffer int16 alocado width*height (caller deve free()).
 */
int16_t* mo_decompress_lossless_ch(const uint8_t *data, int data_size,
                                    int width, int height) {
    if (!data || data_size < 8) return NULL;

    int n_blocks = (int)( data[0]
                        | ((uint32_t)data[1] <<  8)
                        | ((uint32_t)data[2] << 16)
                        | ((uint32_t)data[3] << 24) );
    int pw = (int)(data[4] | (data[5] << 8));
    int ph = (int)(data[6] | (data[7] << 8));

    int bw = (width  + MO_BLOCK_SIZE - 1) / MO_BLOCK_SIZE;
    int bh = (height + MO_BLOCK_SIZE - 1) / MO_BLOCK_SIZE;
    int total_blocks = bw * bh;

    int16_t *padded = (int16_t *)calloc(pw * ph, sizeof(int16_t));
    if (!padded) return NULL;

    int *spiral_r = (int *)malloc(total_blocks * sizeof(int));
    int *spiral_c = (int *)malloc(total_blocks * sizeof(int));
    if (!spiral_r || !spiral_c) {
        free(padded); free(spiral_r); free(spiral_c); return NULL;
    }
    mo_spiral_order(pw, ph, spiral_r, spiral_c, total_blocks);

    int16_t prev_block[64];
    int has_prev = 0;
    int in_pos = 8;
    int i, j;

    for (int b = 0; b < n_blocks && in_pos < data_size; b++) {
        int br = spiral_r[b];
        int bc = spiral_c[b];
        int py = br * MO_BLOCK_SIZE;
        int px = bc * MO_BLOCK_SIZE;

        uint8_t used_delta = data[in_pos++];
        if (in_pos + 2 > data_size) break;
        int rle_size = (int)(data[in_pos] | (data[in_pos + 1] << 8));
        in_pos += 2;
        if (in_pos + rle_size > data_size) break;

        int16_t residuals[64];
        memset(residuals, 0, sizeof(residuals));
        mo_rle_decode(&data[in_pos], rle_size, residuals, 64);
        in_pos += rle_size;

        /* Reconstroi bloco */
        int16_t curr[64];
        if (used_delta && has_prev) {
            for (int k = 0; k < 64; k++)
                curr[k] = residuals[k] + prev_block[k];
        } else {
            memcpy(curr, residuals, 64 * sizeof(int16_t));
        }

        /* Coloca bloco na imagem padded */
        for (i = 0; i < MO_BLOCK_SIZE; i++)
            for (j = 0; j < MO_BLOCK_SIZE; j++)
                padded[(py + i) * pw + (px + j)] = curr[i * MO_BLOCK_SIZE + j];

        memcpy(prev_block, curr, 64 * sizeof(int16_t));
        has_prev = 1;
    }

    /* Extrai area util */
    int16_t *output = (int16_t *)malloc(width * height * sizeof(int16_t));
    if (output) {
        for (i = 0; i < height; i++)
            for (j = 0; j < width; j++)
                output[i * width + j] = padded[i * pw + j];
    }

    free(padded);
    free(spiral_r);
    free(spiral_c);
    return output;
}

/* Calcula PSNR entre canal original (double) e restaurado (double). */
double mo_psnr(const double *original, const double *restored,
               int size, double max_val) {
    double mse = 0.0;
    int i;
    for (i = 0; i < size; i++) {
        double diff = original[i] - restored[i];
        mse += diff * diff;
    }
    mse /= size;
    if (mse < 1e-10) return 999.99;  /* lossless / praticamente lossless */
    return 10.0 * log10((max_val * max_val) / mse);
}

/* ===== Processamento completo de canal ===== */

uint8_t* mo_compress_channel(const double *channel, int width, int height,
                             const double *quant_table, int quality,
                             int *compressed_size, MOStats *stats) {
    int bw = (width + 7) / 8;
    int bh = (height + 7) / 8;
    int total_blocks = bw * bh;
    int pw = bw * 8;
    int ph = bh * 8;

    /* Padding da imagem */
    double *padded = (double *)calloc(pw * ph, sizeof(double));
    if (!padded) { *compressed_size = 0; return NULL; }

    int i, j;
    for (i = 0; i < height; i++) {
        for (j = 0; j < width; j++) {
            padded[i * pw + j] = channel[i * width + j];
        }
        /* Edge padding */
        for (j = width; j < pw; j++) {
            padded[i * pw + j] = channel[i * width + (width - 1)];
        }
    }
    for (i = height; i < ph; i++) {
        memcpy(&padded[i * pw], &padded[(height - 1) * pw], pw * sizeof(double));
    }

    /* Gera ordem Middle-Out */
    int *spiral_r = (int *)malloc(total_blocks * sizeof(int));
    int *spiral_c = (int *)malloc(total_blocks * sizeof(int));
    int n_blocks = mo_spiral_order(pw, ph, spiral_r, spiral_c, total_blocks);

    /* Buffers para blocos quantizados */
    int16_t *prev_quant = NULL;
    int16_t *curr_quant = (int16_t *)malloc(64 * sizeof(int16_t));
    int16_t *encoded = (int16_t *)malloc(64 * sizeof(int16_t));

    /* Buffer de saida (estimativa generosa) */
    int max_out = total_blocks * 200 + 16;
    uint8_t *output = (uint8_t *)malloc(max_out);
    int out_pos = 0;

    /* Header: numero de blocos, dimensoes */
    output[out_pos++] = (uint8_t)(n_blocks & 0xFF);
    output[out_pos++] = (uint8_t)((n_blocks >> 8) & 0xFF);
    output[out_pos++] = (uint8_t)((n_blocks >> 16) & 0xFF);
    output[out_pos++] = (uint8_t)((n_blocks >> 24) & 0xFF);

    /* Stats */
    if (stats) {
        memset(stats, 0, sizeof(MOStats));
        stats->total_blocks = n_blocks;
    }

    long total_coeffs = 0, zero_coeffs = 0;

    for (int b = 0; b < n_blocks; b++) {
        int br = spiral_r[b];
        int bc = spiral_c[b];
        int py = br * 8;
        int px = bc * 8;

        /* Extrai bloco e subtrai 128 */
        double block[64];
        for (i = 0; i < 8; i++)
            for (j = 0; j < 8; j++)
                block[i * 8 + j] = padded[(py + i) * pw + (px + j)] - 128.0;

        /* Fator adaptativo baseado na complexidade do bloco */
        double adapt = mo_adaptive_quant_factor(block, 64, quality);

        /* DCT */
        double dct_block[64];
        mo_dct8x8(block, dct_block);

        /* Quantizacao */
        mo_quantize(dct_block, curr_quant, quant_table, adapt);

        /* Delta prediction */
        int used_delta = mo_delta_encode(curr_quant, prev_quant, encoded);

        /* Flag: 1 byte indicando se usou delta */
        output[out_pos++] = (uint8_t)used_delta;

        /* Fator adaptativo compactado (1 byte, escala 0-255) */
        uint8_t adapt_byte = (uint8_t)(adapt * 25.5);
        if (adapt > 10.0) adapt_byte = 255;
        output[out_pos++] = adapt_byte;

        /* RLE */
        int rle_size = mo_rle_encode(encoded, 64,
                                     &output[out_pos + 2], max_out - out_pos - 2);
        /* Tamanho do RLE (2 bytes) */
        output[out_pos++] = (uint8_t)(rle_size & 0xFF);
        output[out_pos++] = (uint8_t)((rle_size >> 8) & 0xFF);
        out_pos += rle_size;

        /* Estatisticas */
        int is_zero = 1;
        for (i = 0; i < 64; i++) {
            total_coeffs++;
            if (curr_quant[i] == 0) zero_coeffs++;
            else is_zero = 0;
        }
        if (stats) {
            if (is_zero) stats->zero_blocks++;
            if (used_delta) stats->predicted_blocks++;
            double energy = 0;
            for (i = 0; i < 64; i++)
                energy += (double)curr_quant[i] * curr_quant[i];
            stats->avg_energy += energy;
        }

        /* Atualiza referencia para o proximo bloco */
        if (!prev_quant)
            prev_quant = (int16_t *)malloc(64 * sizeof(int16_t));
        memcpy(prev_quant, curr_quant, 64 * sizeof(int16_t));
    }

    if (stats && n_blocks > 0) {
        stats->avg_energy /= n_blocks;
        stats->sparsity = total_coeffs > 0 ?
            (double)zero_coeffs / total_coeffs * 100.0 : 0;
    }

    *compressed_size = out_pos;

    free(padded);
    free(spiral_r);
    free(spiral_c);
    free(curr_quant);
    free(encoded);
    free(prev_quant);

    /* Shrink output */
    output = (uint8_t *)realloc(output, out_pos);
    return output;
}

double* mo_decompress_channel(const uint8_t *compressed, int compressed_size,
                              int width, int height,
                              const double *quant_table, int quality) {
    int bw = (width + 7) / 8;
    int bh = (height + 7) / 8;
    int pw = bw * 8;
    int ph = bh * 8;
    int total_blocks = bw * bh;

    double *padded = (double *)calloc(pw * ph, sizeof(double));
    if (!padded) return NULL;

    int in_pos = 0;

    /* Le numero de blocos */
    int n_blocks = compressed[0] | (compressed[1] << 8) |
                   (compressed[2] << 16) | (compressed[3] << 24);
    in_pos = 4;

    /* Gera ordem Middle-Out (mesma que na compressao) */
    int *spiral_r = (int *)malloc(total_blocks * sizeof(int));
    int *spiral_c = (int *)malloc(total_blocks * sizeof(int));
    mo_spiral_order(pw, ph, spiral_r, spiral_c, total_blocks);

    int16_t *prev_quant = NULL;
    int16_t curr_quant[64];
    int16_t decoded_rle[64];
    int i, j;

    for (int b = 0; b < n_blocks && in_pos < compressed_size; b++) {
        int br = spiral_r[b];
        int bc = spiral_c[b];
        int py = br * 8;
        int px = bc * 8;

        /* Le flag de delta */
        uint8_t used_delta = compressed[in_pos++];

        /* Le fator adaptativo */
        uint8_t adapt_byte = compressed[in_pos++];
        double adapt = adapt_byte / 25.5;

        /* Le tamanho RLE */
        int rle_size = compressed[in_pos] | (compressed[in_pos + 1] << 8);
        in_pos += 2;

        /* Decodifica RLE */
        mo_rle_decode(&compressed[in_pos], rle_size, decoded_rle, 64);
        in_pos += rle_size;

        /* Delta decode */
        if (used_delta && prev_quant) {
            mo_delta_decode(decoded_rle, prev_quant, curr_quant);
        } else {
            memcpy(curr_quant, decoded_rle, 64 * sizeof(int16_t));
        }

        /* Dequantizacao */
        double dct_block[64];
        mo_dequantize(curr_quant, dct_block, quant_table, adapt);

        /* IDCT */
        double block[64];
        mo_idct8x8(dct_block, block);

        /* Escreve bloco + 128 */
        for (i = 0; i < 8; i++) {
            for (j = 0; j < 8; j++) {
                double val = block[i * 8 + j] + 128.0;
                if (val < 0) val = 0;
                if (val > 255) val = 255;
                padded[(py + i) * pw + (px + j)] = val;
            }
        }

        /* Atualiza referencia */
        if (!prev_quant)
            prev_quant = (int16_t *)malloc(64 * sizeof(int16_t));
        memcpy(prev_quant, curr_quant, 64 * sizeof(int16_t));
    }

    /* Extrai area util */
    double *output = (double *)malloc(width * height * sizeof(double));
    if (output) {
        for (i = 0; i < height; i++)
            for (j = 0; j < width; j++)
                output[i * width + j] = padded[i * pw + j];
    }

    free(padded);
    free(spiral_r);
    free(spiral_c);
    free(prev_quant);

    return output;
}
