(function(global) {
    'use strict';

    if (!global) {
        return;
    }

    const STOPWORDS = new Set([
        'a', 'ao', 'aos', 'as', 'ate', 'com', 'como', 'da', 'das', 'de', 'do', 'dos', 'e', 'em',
        'entre', 'essa', 'esse', 'esta', 'este', 'isto', 'la', 'lo', 'mais', 'mas', 'na', 'nas',
        'no', 'nos', 'o', 'os', 'ou', 'para', 'pela', 'pelas', 'pelo', 'pelos', 'por', 'pra',
        'pro', 'qual', 'quais', 'quanto', 'quantos', 'quantas', 'que', 'se', 'sem', 'sobre', 'sua', 'suas', 'te', 'um', 'uma',
        'umas', 'uns', 'queria', 'quero', 'saber', 'mostrar', 'ver', 'ultimo', 'ultimos',
        'ultima', 'ultimas', 'historico', 'historia', 'importacao', 'importacoes', 'codigo',
        'cod', 'produto', 'produtos', 'informacao', 'informacoes', 'estoque', 'buscar',
        'procurar', 'saber', 'sobre', 'quando', 'onde', 'porque', 'diga', 'dizer', 'preciso',
        'precisava', 'poderia', 'pode', 'favor', 'ajuda', 'ajudar', 'informe', 'informar',
        'descubra', 'descobrir', 'foi', 'sera', 'será', 'era'
    ]);

    const SUPPLIER_KEYWORDS = [
        'fornecedor', 'fornecedores', 'representante', 'representantes', 'fabricante',
        'fabricantes', 'distribuidor', 'distribuidores', 'parceiro', 'parceiros',
        'produtor', 'produtora', 'fabricacao', 'fabrica', 'fabricam', 'fabricado',
        'fabricados', 'produz', 'produzem'
    ];

    const HISTORY_KEYWORDS = [
        'historico', 'historicos', 'historia', 'ultima', 'ultimas', 'ultimo', 'ultimos',
        'importacao', 'importacoes', 'embarque', 'embarques', 'compra', 'compras',
        'entrega', 'entregas', 'recebimento', 'recebemos', 'chegou', 'entrada'
    ];

    const STOCK_KEYWORDS = [
        'estoque', 'quantidade', 'qtd', 'saldo', 'disponivel', 'disponiveis', 'tem', 'possui',
        'restante', 'resta', 'sobra', 'sobrando', 'disponibilidade'
    ];

    const CLASSIFICATION_KEYWORDS = [
        'classe', 'classificacao', 'classifica', 'abc', 'segmentacao', 'segmento'
    ];

    const FAMILY_KEYWORDS = [
        'familia', 'linha', 'linhas', 'grupo de produtos', 'grupo do produto', 'grupo do',
        'categoria', 'categoria de produtos', 'segmento', 'segmento do produto', 'grupo do item'
    ];

    const ACTION_KEYWORDS_SET = new Set(
        SUPPLIER_KEYWORDS
            .concat(HISTORY_KEYWORDS, STOCK_KEYWORDS, CLASSIFICATION_KEYWORDS, FAMILY_KEYWORDS)
    );

    const QUESTION_KEYWORDS = ['qual', 'quais', 'quem', 'como', 'quando', 'onde', 'quanto', 'quantos', 'quantas'];

    function normalizeText(value) {
        if (value === null || typeof value === 'undefined') {
            return '';
        }

        return value
            .toString()
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLowerCase();
    }

    function tokenize(value) {
        const normalized = normalizeText(value);
        if (!normalized) {
            return [];
        }

        return normalized
            .split(/[^a-z0-9]+/)
            .filter(function(token) {
                return token && token.length > 1 && !STOPWORDS.has(token);
            });
    }

    function extractCodeCandidates(rawQuery) {
        if (typeof rawQuery !== 'string' || rawQuery.trim() === '') {
            return [];
        }

        const normalized = normalizeText(rawQuery);
        const matches = normalized.match(/[a-z0-9]{2,}(?:[.\-/][a-z0-9]{1,})*/g) || [];

        return matches
            .map(function(match) {
                return match.replace(/[^a-z0-9]/g, '');
            })
            .filter(function(candidate) {
                return candidate && candidate.length > 1 && /\d/.test(candidate);
            });
    }

    const productIndexCache = new WeakMap();

    function getProductIndex(product) {
        if (!product || typeof product !== 'object') {
            return null;
        }

        if (productIndexCache.has(product)) {
            return productIndexCache.get(product);
        }

        const code = normalizeText(product.code || '');
        const index = {
            code: code,
            codeCompact: code.replace(/[^a-z0-9]/g, ''),
            item: normalizeText(product.item || ''),
            supplier: normalizeText(product.supplier || ''),
            family: normalizeText(product.family || ''),
            tokens: tokenize(product.item || '')
        };

        productIndexCache.set(product, index);
        return index;
    }

    function detectIntent(normalizedQuery, tokens, codeCandidates) {
        const safeNormalized = typeof normalizedQuery === 'string' ? normalizedQuery : '';
        const lowerQuery = safeNormalized.toLowerCase();
        const hasSupplierKeyword = SUPPLIER_KEYWORDS.some(function(keyword) {
            return lowerQuery.includes(keyword);
        });
        const hasHistoryKeyword = HISTORY_KEYWORDS.some(function(keyword) {
            return lowerQuery.includes(keyword);
        });
        const hasStockKeyword = STOCK_KEYWORDS.some(function(keyword) {
            return lowerQuery.includes(keyword);
        });
        const hasClassKeyword = CLASSIFICATION_KEYWORDS.some(function(keyword) {
            return lowerQuery.includes(keyword);
        });
        const hasFamilyKeyword = FAMILY_KEYWORDS.some(function(keyword) {
            return lowerQuery.includes(keyword);
        });
        let intent = 'search';
        let desiredEntity = null;

        if (hasSupplierKeyword && !hasHistoryKeyword) {
            intent = 'ask_supplier';
            desiredEntity = 'supplier';
        } else if (hasHistoryKeyword && !hasSupplierKeyword) {
            intent = 'ask_history';
            desiredEntity = 'history';
        } else if (hasStockKeyword && !hasSupplierKeyword && !hasHistoryKeyword) {
            intent = 'ask_stock';
            desiredEntity = 'stock';
        } else if (hasSupplierKeyword && hasHistoryKeyword) {
            // Supplier questions that also mention history default to supplier intent
            intent = 'ask_supplier';
            desiredEntity = 'supplier';
        }

        if (intent === 'search') {
            if (hasClassKeyword) {
                intent = 'ask_class';
                desiredEntity = 'classification';
            } else if (hasFamilyKeyword) {
                intent = 'ask_family';
                desiredEntity = 'family';
            }
        }

        const focusTokens = [];
        const actionTokens = [];

        (tokens || []).forEach(function(token) {
            if (ACTION_KEYWORDS_SET.has(token)) {
                actionTokens.push(token);
            } else {
                focusTokens.push(token);
            }
        });

        if (focusTokens.length === 0 && Array.isArray(codeCandidates) && codeCandidates.length > 0) {
            focusTokens.push(codeCandidates[0]);
        }

        const hasQuestionWord = QUESTION_KEYWORDS.some(function(keyword) {
            return lowerQuery.includes(keyword);
        });

        return {
            intent: intent,
            desiredEntity: desiredEntity,
            focusTokens: focusTokens,
            actionTokens: actionTokens,
            hasQuestionWord: hasQuestionWord
        };
    }

    function buildContext(rawQuery) {
        const safeQuery = typeof rawQuery === 'string' ? rawQuery : '';
        const normalized = normalizeText(safeQuery);
        const tokens = tokenize(safeQuery);
        const codeCandidates = extractCodeCandidates(safeQuery);
        const codeCandidateSet = new Set(codeCandidates);
        const keywordSet = new Set();

        tokens.forEach(function(token) {
            if (token.length > 1) {
                keywordSet.add(token);
            }
        });

        codeCandidates.forEach(function(candidate) {
            if (candidate.length > 1) {
                keywordSet.add(candidate);
            }
        });

        const keywords = Array.from(keywordSet);
        const highlightTerm = codeCandidates[0] || (tokens[0] || normalized);
        const hasMeaning = keywords.length > 0 && highlightTerm.trim() !== '';
        const intentInfo = detectIntent(normalized, tokens, codeCandidates);

        return {
            rawQuery: safeQuery,
            normalized: normalized,
            tokens: tokens,
            codeCandidates: codeCandidates,
            codeCandidateSet: codeCandidateSet,
            keywords: keywords,
            highlightTerm: highlightTerm,
            hasMeaning: hasMeaning,
            scoreCache: new WeakMap(),
            intent: intentInfo.intent,
            intentMeta: intentInfo,
            focusTokens: intentInfo.focusTokens
        };
    }

    function computeScore(product, context) {
        if (!context || !context.hasMeaning) {
            return 0;
        }

        const index = getProductIndex(product);
        if (!index) {
            return 0;
        }

        let score = 0;
        const matchedTerms = new Set();
        const codeCandidates = context.codeCandidates || [];

        codeCandidates.forEach(function(candidate) {
            if (!candidate) {
                return;
            }

            if (index.codeCompact === candidate) {
                score += 160;
                matchedTerms.add(candidate);
            } else if (index.codeCompact.includes(candidate)) {
                score += 110;
                matchedTerms.add(candidate);
            } else if (index.item.includes(candidate)) {
                score += 70;
                matchedTerms.add(candidate);
            }
        });

        const tokens = context.tokens || [];
        tokens.forEach(function(token) {
            if (!token) {
                return;
            }

            const isCode = context.codeCandidateSet && context.codeCandidateSet.has(token);
            let matched = false;

            if (index.item.includes(token)) {
                matched = true;
                score += isCode ? 40 : 50;

                const startsWithToken = index.tokens.some(function(entry) {
                    return entry.startsWith(token);
                });

                if (startsWithToken) {
                    score += 10;
                }
            }

            if (index.family.includes(token)) {
                matched = true;
                score += 25;
            }

            if (index.supplier.includes(token)) {
                matched = true;
                score += 20;
            }

            if (!matched && index.codeCompact.includes(token)) {
                matched = true;
                score += 35;
            }

            if (matched) {
                matchedTerms.add(token);
            }
        });

        if (matchedTerms.size >= Math.min(2, context.keywords.length)) {
            score += 20;
        } else if (matchedTerms.size > 0) {
            score += 10;
        }

        if (context.highlightTerm) {
            const highlight = context.highlightTerm;
            if (index.item.startsWith(highlight)) {
                score += 12;
            }
            if (!index.item.includes(highlight) && index.codeCompact.includes(highlight)) {
                score += 8;
            }
        }

        return score;
    }

    function getProductScore(product, context) {
        if (!context || !context.hasMeaning || !product) {
            return 0;
        }

        let cache = context.scoreCache;
        if (!(cache instanceof WeakMap)) {
            cache = new WeakMap();
            context.scoreCache = cache;
        }

        if (cache.has(product)) {
            return cache.get(product);
        }

        const score = computeScore(product, context);
        cache.set(product, score);
        return score;
    }

    function matchesProduct(product, context) {
        if (!context || !context.hasMeaning) {
            return false;
        }

        return getProductScore(product, context) > 0;
    }

    function rankProducts(products, context, limit) {
        if (!Array.isArray(products) || !context || !context.hasMeaning) {
            return [];
        }

        const scored = products.map(function(product) {
            return {
                product: product,
                score: getProductScore(product, context)
            };
        }).filter(function(entry) {
            return entry.score > 0;
        });

        scored.sort(function(a, b) {
            if (b.score !== a.score) {
                return b.score - a.score;
            }

            const nameA = (a.product.item || a.product.code || '').toString();
            const nameB = (b.product.item || b.product.code || '').toString();
            return nameA.localeCompare(nameB, 'pt-BR', { sensitivity: 'base' });
        });

        if (typeof limit === 'number' && limit > 0) {
            return scored.slice(0, limit);
        }

        return scored;
    }

    function textMatchesContext(text, context) {
        if (!context || !context.hasMeaning) {
            return false;
        }

        const normalized = normalizeText(text);
        if (!normalized) {
            return false;
        }

        const keywords = context.keywords || [];
        for (let index = 0; index < keywords.length; index += 1) {
            const keyword = keywords[index];
            if (keyword && normalized.includes(keyword)) {
                return true;
            }
        }

        const highlight = context.highlightTerm ? context.highlightTerm.toLowerCase() : '';
        return Boolean(highlight && normalized.includes(highlight));
    }

    global.searchIntelligence = {
        buildContext: buildContext,
        rankProducts: rankProducts,
        matchesProduct: matchesProduct,
        textMatchesContext: textMatchesContext,
        normalizeText: normalizeText
    };
})(typeof window !== 'undefined' ? window : null);
