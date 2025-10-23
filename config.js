(function(window) {
    window.DASHBOARD_CONFIG = window.DASHBOARD_CONFIG || {};

    window.DASHBOARD_CONFIG.familyColors = Object.assign({
        /**
         * Defina aqui as cores usadas no histórico de produto.
         * - "palette": ordem das cores aplicadas automaticamente às famílias.
         * - "overrides": cores fixas por nome da família.
         * - "fallback": cor padrão caso a paleta seja insuficiente.
         *
         * Exemplo de uso:
         *   overrides: {
         *     'Borracha Silicone': '#ff8800',
         *     'Minha Família': '#123abc'
         *   },
         *   palette: ['#001f3f', '#0074D9']
         */
        palette: [
            '#FF6F61',
            '#1a7d73',
            '#F2994A',
            '#9B51E0',
            '#56CCF2',
            '#27AE60',
            '#F2C94C',
            '#BB6BD9',
            '#1a7d73',
            '#2D9CDB'
        ],
        overrides: {
            'Borracha Silicone': '#282f99',
            'Borracha de Silicone': '#282f99',
            'ADITIVO BORRACHA': '#1a7d73',
            'BORRACHA EVA': '#c9662c',
            'BORRACHA EPDM': '#8d22a8',
            'ADITIVO EVA': '#3b87ad'
        },
        fallback: '#1d396e'
    }, window.DASHBOARD_CONFIG.familyColors || {});
})(window);
