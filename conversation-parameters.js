(function(global) {
    'use strict';

    if (!global) {
        return;
    }

    function normalize(value) {
        if (value === null || typeof value === 'undefined') {
            return '';
        }

        return value
            .toString()
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLowerCase();
    }

    function mapPattern(pattern) {
        const copy = Object.assign({}, pattern);
        copy.normalizedPhrases = (pattern.phrases || []).map(normalize);
        copy.requireFocus = typeof pattern.requireFocus === 'number'
            ? pattern.requireFocus
            : (typeof pattern.minFocus === 'number' ? pattern.minFocus : 0);
        return copy;
    }

    function includesAny(haystack, needles) {
        if (!haystack || !Array.isArray(needles)) {
            return false;
        }

        for (let index = 0; index < needles.length; index += 1) {
            const needle = needles[index];
            if (needle && haystack.includes(needle)) {
                return true;
            }
        }

        return false;
    }

    const EXACT_QUESTION_PATTERNS = [
        {
            intent: 'ask_supplier',
            phrases: [
                'qual o fornecedor',
                'qual a fornecedora',
                'qual e o fornecedor',
                'qual e a fornecedora',
                'qual fornecedor',
                'qual fornecedora',
                'qual o fabricante',
                'qual e o fabricante',
                'qual fabricante do',
                'qual distribuidor do',
                'qual o distribuidor',
                'qual o parceiro comercial',
                'quem e o fornecedor',
                'quem e a fornecedora',
                'quem fornece',
                'quem distribui',
                'quem fabrica',
                'quem produz',
                'quem entrega',
                'me diz o fornecedor',
                'me informe o fornecedor',
                'pode dizer o fornecedor',
                'preciso do fornecedor',
                'fornecedor do',
                'fornecedor da',
                'fornecedor de',
                'representante do',
                'representante da',
                'representante de',
                'distribuidor do',
                'distribuidor da',
                'distribuidor de'
            ],
            minTokens: 1,
            requireFocus: 1,
            requireQuestion: false
        },
        {
            intent: 'ask_history',
            phrases: [
                'ultima importacao',
                'ultima compra',
                'ultima venda',
                'ultimo embarque',
                'quando foi a ultima',
                'quando foi o ultimo',
                'qual foi a ultima importacao',
                'qual foi a ultima compra',
                'qual foi o ultimo embarque',
                'quando chegou o ultimo',
                'quando recebemos',
                'quando veio',
                'quando entrou',
                'ultima entrega do',
                'historico do',
                'historico da',
                'historico de',
                'mostrar historico',
                'me mostra o historico',
                'exibir historico',
                'ver historico',
                'me traga o historico',
                'preciso do historico',
                'pode mostrar o historico',
                'quero rever a ultima importacao',
                'quero saber a ultima importacao',
                'quero saber quando foi a ultima'
            ],
            minTokens: 1,
            requireFocus: 1,
            requireQuestion: false
        },
        {
            intent: 'ask_stock',
            phrases: [
                'quanto tem em estoque',
                'quantas unidades tem',
                'quantos itens tem',
                'qual o estoque',
                'qual a quantidade em estoque',
                'quanto possui em estoque',
                'quanto temos em estoque',
                'tem disponivel',
                'tem disponibilidade',
                'mostrar estoque',
                'me mostra o estoque',
                'ver estoque',
                'pode informar o estoque',
                'qual a disponibilidade',
                'qual saldo do',
                'quanto resta do',
                'quanto sobra do',
                'quanto esta disponivel',
                'qual a disponibilidade do',
                'mostrar disponibilidade'
            ],
            minTokens: 1,
            requireFocus: 1,
            requireQuestion: false
        },
        {
            intent: 'ask_class',
            phrases: [
                'qual a classe',
                'qual classe abc',
                'qual e a classe',
                'me diga a classe',
                'classe abc do',
                'em qual classe',
                'classificacao abc',
                'qual grupo abc',
                'qual letra abc',
                'classificacao do item',
                'classificacao do produto',
                'em que classe abc se encontra'
            ],
            minTokens: 1,
            requireFocus: 1,
            requireQuestion: false
        },
        {
            intent: 'ask_family',
            phrases: [
                'qual a familia',
                'de qual familia',
                'qual a linha',
                'qual categoria do produto',
                'essa familia',
                'pertence a qual familia',
                'linha de produto',
                'qual grupo do produto',
                'qual segmento pertence',
                'qual categoria pertence',
                'grupo do item'
            ],
            minTokens: 1,
            requireFocus: 1,
            requireQuestion: false
        }
    ].map(mapPattern);

    function resolveConversation(context) {
        if (!context) {
            return {
                isConversational: false,
                expectExact: false,
                intent: null,
                pattern: null
            };
        }

        const rawQuery = typeof context.rawQuery === 'string' ? context.rawQuery : '';
        const normalizedRaw = normalize(rawQuery);
        const tokens = Array.isArray(context.tokens) ? context.tokens : [];
        const focusTokens = Array.isArray(context.focusTokens)
            ? context.focusTokens.filter(Boolean)
            : [];
        const codeCandidates = Array.isArray(context.codeCandidates) ? context.codeCandidates : [];
        const hasQuestionMark = /\?\s*$/.test(rawQuery);
        const hasQuestionWord = Boolean(context.intentMeta && context.intentMeta.hasQuestionWord);

        const wordCount = normalizedRaw.trim() !== ''
            ? normalizedRaw.trim().split(/\s+/).length
            : 0;

        const conversationalBaseline = hasQuestionWord || hasQuestionMark || wordCount >= 4;

        let matchedPattern = null;
        let expectExact = false;

        for (let index = 0; index < EXACT_QUESTION_PATTERNS.length; index += 1) {
            const pattern = EXACT_QUESTION_PATTERNS[index];
            if (pattern.intent && pattern.intent !== context.intent) {
                continue;
            }

            if (pattern.requireFocus > 0 && focusTokens.length < pattern.requireFocus && codeCandidates.length < pattern.requireFocus) {
                continue;
            }

            if (pattern.requireQuestion && !(hasQuestionWord || hasQuestionMark)) {
                continue;
            }

            if (pattern.minTokens && tokens.length < pattern.minTokens) {
                continue;
            }

            if (!includesAny(normalizedRaw, pattern.normalizedPhrases)) {
                continue;
            }

            matchedPattern = pattern;
            expectExact = true;
            break;
        }

        if (!expectExact && (context.intent === 'ask_supplier' || context.intent === 'ask_history' || context.intent === 'ask_stock')) {
            const confidentFocus = focusTokens.length === 1 || codeCandidates.length === 1;
            if ((hasQuestionWord || hasQuestionMark) && confidentFocus) {
                expectExact = true;
            }
        }

        return {
            isConversational: conversationalBaseline || expectExact,
            expectExact: expectExact,
            intent: context.intent,
            pattern: matchedPattern,
            hasQuestionWord: hasQuestionWord,
            hasQuestionMark: hasQuestionMark
        };
    }

    global.conversationParameters = {
        exactQuestionPatterns: EXACT_QUESTION_PATTERNS,
        resolve: resolveConversation,
        normalize: normalize
    };
})(typeof window !== 'undefined' ? window : null);
