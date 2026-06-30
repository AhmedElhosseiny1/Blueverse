/* Blueverse Dashboard — index.html controller */
(function () {
  'use strict';

  const fmtMoney = (v) => 'AED ' + Math.round(Number(v || 0)).toLocaleString();
  const fmtNum = (v, d = 0) => Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: d });

  function sum(arr) {
    return (arr || []).reduce((a, b) => a + (Number(b) || 0), 0);
  }

  function render() {
    const data = (typeof REPORT_DATA !== 'undefined' ? REPORT_DATA : window.REPORT_DATA);
    if (!data) return;

    // Paid-media totals
    const googleSpend = sum(data.googleMonthly && data.googleMonthly.spend);
    const googleConv = sum(data.googleMonthly && data.googleMonthly.conversions);
    const metaSpend = sum(data.metaCampaigns && data.metaCampaigns.spend);
    const metaConv = sum(data.metaCampaigns && data.metaCampaigns.conversations);
    const totalSpend = googleSpend + metaSpend;
    const platformEvents = googleConv + metaConv;

    const googleImpr = sum(
      data.explorer && data.explorer.google &&
      data.explorer.google.day &&
      data.explorer.google.day.series &&
      data.explorer.google.day.series['All Google campaigns'] &&
      data.explorer.google.day.series['All Google campaigns'].metrics &&
      data.explorer.google.day.series['All Google campaigns'].metrics.Impressions
    );
    const metaImpr = sum(
      data.explorer && data.explorer.meta &&
      data.explorer.meta.month &&
      data.explorer.meta.month.series &&
      data.explorer.meta.month.series['All Meta campaigns'] &&
      data.explorer.meta.month.series['All Meta campaigns'].metrics &&
      data.explorer.meta.month.series['All Meta campaigns'].metrics.Impressions
    );
    const totalImpressions = googleImpr + metaImpr;

    // Respond.io totals
    const contacts = data.respondContacts || [];
    const paidContacts = contacts.length;
    const paidJune = contacts.filter(c => c && c.date && c.date.startsWith('2026-06')).length;

    // CRM value totals
    const quotedValue = contacts.reduce((a, c) => a + (Number(c.quotedValue) || 0), 0);
    const finalSaleValue = contacts.reduce((a, c) => a + (Number(c.finalSaleValue) || 0), 0);
    const quotedCount = contacts.filter(c => Number(c.quotedValue) > 0).length;
    const saleCount = contacts.filter(c => Number(c.finalSaleValue) > 0).length;

    const blendedCpe = platformEvents > 0 ? totalSpend / platformEvents : 0;

    // Hero KPIs
    const hero = document.getElementById('heroKpis');
    if (hero) {
      hero.innerHTML = [
        { cls: 'blue', label: 'Total paid spend', val: fmtMoney(totalSpend), small: 'Google + Meta' },
        { cls: 'cyan', label: 'Total impressions', val: fmtNum(totalImpressions), small: 'Cross-channel reach signal' },
        { cls: 'green', label: 'Platform lead events', val: fmtNum(platformEvents), small: 'Google conv. + Meta msg starts' },
        { cls: 'orange', label: 'Respond.io paid contacts', val: fmtNum(paidContacts), small: `${fmtNum(paidJune)} in June 2026` },
        { cls: 'violet', label: 'Blended cost / event', val: fmtMoney(blendedCpe), small: 'Spend divided by platform lead events' }
      ].map(k => `
        <article class="kpi ${k.cls}">
          <span>${k.label}</span>
          <strong>${k.val}</strong>
          ${k.small ? `<small>${k.small}</small>` : ''}
        </article>
      `).join('');
    }

    // Overview KPIs
    const setText = (id, strong, small) => {
      const el = document.getElementById(id);
      if (!el) return;
      const s = el.querySelector('strong');
      const sm = el.querySelector('small');
      if (s) s.textContent = strong;
      if (sm) sm.textContent = small;
    };

    setText('kpiGoogleSpend', fmtMoney(googleSpend), `${fmtNum(googleConv)} conversions; AED ${googleConv > 0 ? Math.round(googleSpend / googleConv) : 0} CPL`);
    setText('kpiMetaSpend', fmtMoney(metaSpend), `${fmtNum(metaConv)} msg starts; AED ${metaConv > 0 ? (metaSpend / metaConv).toFixed(2) : 0} cost/msg`);
    setText('kpiQuotedValue', fmtMoney(quotedValue), `${fmtNum(quotedCount)} contacts with quote value`);
    setText('kpiFinalSaleValue', fmtMoney(finalSaleValue), `${fmtNum(saleCount)} contacts with sale value`);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', render);
  } else {
    render();
  }
})();
