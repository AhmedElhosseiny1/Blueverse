function initExplorer() {
      const channelSel = document.getElementById('explorerChannel');
      const granSel = document.getElementById('explorerGranularity');
      const campSel = document.getElementById('explorerCampaign');
      const m1Sel = document.getElementById('explorerMetric1');
      const m2Sel = document.getElementById('explorerMetric2');
      const metricLabels = {
        Cost: 'Spend / cost', Spend: 'Spend', Impressions: 'Impressions', Clicks: 'Clicks',
        Conversions: 'Conversions / msg starts', CTR: 'CTR %', CPC: 'CPC', CPL: 'CPL / cost per event',
        CPM: 'CPM', CVR: 'CVR %', Reach: 'Reach', CPMC: 'Cost per message', Frequency: 'Frequency'
      };

      function activePayload() {
        const channel = channelSel.value;
        let granularity = granSel.value;
        if (channel === 'meta') granularity = 'month';
        return REPORT_DATA.explorer[channel][granularity] || REPORT_DATA.explorer[channel].month;
      }

      function refill() {
        const channel = channelSel.value;
        [...granSel.options].forEach(opt => opt.disabled = channel === 'meta' && opt.value !== 'month');
        if (channel === 'meta') granSel.value = 'month';
        const payload = activePayload();
        const names = Object.keys(payload.series);
        campSel.innerHTML = names.map(name => `<option value="${name.replace(/"/g, '&quot;')}">${name}</option>`).join('');
        const first = payload.series[names[0]];
        const metrics = Object.keys(first.metrics || {});
        m1Sel.innerHTML = metrics.map(m => `<option value="${m}">${metricLabels[m] || m}</option>`).join('');
        m2Sel.innerHTML = metrics.map(m => `<option value="${m}">${metricLabels[m] || m}</option>`).join('');
        m1Sel.value = metrics.includes('Cost') ? 'Cost' : metrics[0];
        m2Sel.value = metrics.includes('Conversions') ? 'Conversions' : metrics[1] || metrics[0];
        update();
      }

      function update() {
        const payload = activePayload();
        const name = campSel.value || Object.keys(payload.series)[0];
        const s = payload.series[name];
        const periods = payload.periods;
        const metric1 = m1Sel.value;
        const metric2 = m2Sel.value;
        const periodMap = Object.fromEntries((s.periods || []).map((p, i) => [p, i]));
        const valuesFor = metric => periods.map(period => {
          const idx = periodMap[period];
          return idx === undefined ? 0 : Number((s.metrics[metric] || [])[idx] || 0);
        });
        const datasets = [
          {label: metricLabels[metric1] || metric1, data: valuesFor(metric1), color: COLORS.blue},
        ];
        if (metric2 && metric2 !== metric1) datasets.push({label: metricLabels[metric2] || metric2, data: valuesFor(metric2), color: COLORS.orange});
        drawLineChart('explorerChart', {labels: periods, datasets, height: 390});
      }

      channelSel.addEventListener('change', refill);
      granSel.addEventListener('change', refill);
      campSel.addEventListener('change', update);
      m1Sel.addEventListener('change', update);
      m2Sel.addEventListener('change', update);
      refill();
    }

function renderPaid() {
  drawGroupedBars('googleMonthlyChart', {
    labels: REPORT_DATA.googleMonthly.labels,
    datasets: [
      {label: 'Spend', values: REPORT_DATA.googleMonthly.spend, color: COLORS.blue},
      {label: 'Conversions', values: REPORT_DATA.googleMonthly.conversions, color: COLORS.green}
    ]
  });
  drawBarChart('googleCampaignChart', {labels: REPORT_DATA.googleCampaigns.labels, values: REPORT_DATA.googleCampaigns.spend, horizontal: true, color: COLORS.blue, title: 'Spend by campaign'});
  drawGroupedBars('weekdayChart', {
    labels: REPORT_DATA.weekday.labels,
    datasets: [
      {label: 'Spend', values: REPORT_DATA.weekday.spend, color: COLORS.blue},
      {label: 'Conversions', values: REPORT_DATA.weekday.conversions, color: COLORS.green}
    ]
  });
  drawHeatmap();
  drawGroupedBars('metaCampaignChart', {
    labels: REPORT_DATA.metaCampaigns.labels,
    datasets: [
      {label: 'Spend', values: REPORT_DATA.metaCampaigns.spend, color: COLORS.cyan},
      {label: 'Msg starts', values: REPORT_DATA.metaCampaigns.conversations, color: COLORS.orange}
    ]
  });
  drawGroupedBars('metaPlatformChart', {
    labels: REPORT_DATA.metaPlatforms.labels,
    datasets: [
      {label: 'Spend', values: REPORT_DATA.metaPlatforms.spend, color: COLORS.cyan},
      {label: 'Msg starts', values: REPORT_DATA.metaPlatforms.conversations, color: COLORS.orange}
    ]
  });
}
window.addEventListener('resize', () => window.requestAnimationFrame(renderPaid));
initExplorer();
renderPaid();
