(() => {
  'use strict';

  const INDICATORS = ['T1', 'T2', 'E1', 'E2', 'S1', 'S2', 'B1', 'B2', 'C1', 'C2'];
  let radarChart = null;
  let selectedDistrict = '';

  const getState = () => (typeof state !== 'undefined' ? state : window.state || {});
  const select = (selector) => document.querySelector(selector);
  const theme = () => window.QQTheme;

  function render() {
    const currentState = getState();
    const result = currentState.result;
    const selector = select('#district-radar-select');
    const canvas = select('#district-radar');
    if (!selector || !canvas || !result?.valid || !Array.isArray(result.districts)) return;

    if (!selectedDistrict || !result.districts.some((item) => item.id === selectedDistrict)) {
      selectedDistrict = result.min_district_after || result.districts[0]?.id;
    }
    selector.innerHTML = result.districts.map((district) =>
      `<option value="${district.id}" ${district.id === selectedDistrict ? 'selected' : ''}>${district.name}</option>`
    ).join('');

    const district = result.districts.find((item) => item.id === selectedDistrict);
    if (!district) return;
    const names = currentState.catalog?.indicator_names || {};
    const deltas = INDICATORS.map((code) => ({
      code,
      delta: district.indicators_after[code] - district.indicators_before[code],
    }));
    const strongest = [...deltas].sort((a, b) => b.delta - a.delta)[0];
    const weakest = [...INDICATORS].sort(
      (a, b) => district.indicators_after[a] - district.indicators_after[b]
    )[0];
    select('#radar-insight').textContent =
      `Слабое место после мер: ${weakest} — ${names[weakest]} (${district.indicators_after[weakest].toFixed(1)}). ` +
      `Наибольший прирост: ${strongest.code} ${strongest.delta > 0 ? '+' : ''}${strongest.delta.toFixed(1)}.`;

    if (radarChart) radarChart.destroy();
    if (typeof Chart === 'undefined') {
      canvas.classList.add('hidden');
      select('#radar-fallback').classList.remove('hidden');
      return;
    }
    canvas.classList.remove('hidden');
    select('#radar-fallback').classList.add('hidden');
    radarChart = new Chart(canvas, {
      type: 'radar',
      data: {
        labels: INDICATORS,
        datasets: [
          {
            label: 'До',
            data: INDICATORS.map((code) => district.indicators_before[code]),
            borderColor: theme().colors.before,
            backgroundColor: theme().alpha(theme().colors.before, .10),
            pointBackgroundColor: theme().colors.before,
            borderWidth: 2,
          },
          {
            label: 'После',
            data: INDICATORS.map((code) => district.indicators_after[code]),
            borderColor: theme().colors.after,
            backgroundColor: theme().alpha(theme().colors.after, .20),
            pointBackgroundColor: theme().colors.after,
            borderWidth: 3,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom', labels: { usePointStyle: true, padding: 22 } },
          tooltip: {
            callbacks: {
              title: (items) => {
                const code = items[0]?.label;
                return `${code} · ${names[code] || code}`;
              },
            },
          },
        },
        scales: {
          r: {
            min: 0,
            max: 100,
            beginAtZero: true,
            ticks: { stepSize: 20, showLabelBackdrop: false },
            grid: { color: theme().colors.line },
            angleLines: { color: theme().colors.line },
            pointLabels: { color: theme().colors.navy, font: { size: 12, weight: '700' } },
          },
        },
      },
    });
  }

  function mount() {
    const resultScreen = select('#result-screen');
    const selector = select('#district-radar-select');
    if (!resultScreen || !selector) return;
    selector.addEventListener('change', () => {
      selectedDistrict = selector.value;
      render();
    });
    new MutationObserver(() => {
      if (!resultScreen.classList.contains('hidden')) render();
    }).observe(resultScreen, { attributes: true, attributeFilter: ['class'] });
    if (!resultScreen.classList.contains('hidden')) render();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, { once: true });
  else mount();
})();
