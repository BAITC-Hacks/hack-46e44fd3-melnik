(() => {
  'use strict';

  const FALLBACKS = Object.freeze({
    navy: '#0B1F33',
    sky: '#00AFCA',
    sky2: '#E0F6FA',
    gold: '#FEC50C',
    paper: '#F4F6F8',
    card: '#FFFFFF',
    line: '#DDE3E8',
    muted: '#5B6B7A',
    dataLow: '#D64545',
    dataMid: '#F2A541',
    dataHigh: '#2FA37A',
    before: '#B8C2CC',
    transport: '#2563EB',
    ecology: '#16A34A',
    social: '#F97316',
    safety: '#7C3AED',
    services: '#0891B2',
  });

  function css(name, fallback) {
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return value || fallback;
  }

  const colors = {
    get navy() { return css('--navy', FALLBACKS.navy); },
    get sky() { return css('--sky', FALLBACKS.sky); },
    get sky2() { return css('--sky-2', FALLBACKS.sky2); },
    get gold() { return css('--gold', FALLBACKS.gold); },
    get paper() { return css('--paper', FALLBACKS.paper); },
    get card() { return css('--card', FALLBACKS.card); },
    get line() { return css('--line', FALLBACKS.line); },
    get muted() { return css('--muted', FALLBACKS.muted); },
    get low() { return css('--data-low', FALLBACKS.dataLow); },
    get mid() { return css('--data-mid', FALLBACKS.dataMid); },
    get high() { return css('--data-high', FALLBACKS.dataHigh); },
    get before() { return css('--data-before', FALLBACKS.before); },
    get after() { return css('--sky', FALLBACKS.sky); },
  };

  const directions = {
    get 'Транспорт'() { return css('--dir-transport', FALLBACKS.transport); },
    get 'Экология'() { return css('--dir-ecology', FALLBACKS.ecology); },
    get 'Соцсфера'() { return css('--dir-social', FALLBACKS.social); },
    get 'Безопасность'() { return css('--dir-safety', FALLBACKS.safety); },
    get 'Сервисы'() { return css('--dir-services', FALLBACKS.services); },
  };

  window.QQTheme = Object.freeze({
    colors,
    directions,
    get before() { return colors.before; },
    get after() { return colors.after; },
    scale(value) {
      const numeric = Number(value);
      if (!Number.isFinite(numeric) || numeric < 45) return colors.low;
      if (numeric <= 65) return colors.mid;
      return colors.high;
    },
    direction(name) {
      return directions[name] || colors.sky;
    },
    alpha(color, opacity) {
      const hex = String(color).trim().replace('#', '');
      if (!/^[\da-f]{6}$/i.test(hex)) return color;
      const channels = hex.match(/.{2}/g).map((part) => parseInt(part, 16));
      return `rgba(${channels.join(', ')}, ${Math.max(0, Math.min(1, opacity))})`;
    },
    reducedMotion() {
      return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    },
  });
})();
