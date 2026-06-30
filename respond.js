(function () {
  const data = (typeof REPORT_DATA !== 'undefined' ? REPORT_DATA : window.REPORT_DATA) || {};
  const contacts = data.respondContacts || [];
  const options = data.respondFilterOptions || {};
  const funnel = data.respondLifecycleFunnel || [];
  const health = data.respondDataHealth || {};

  const fmtMoney = v => 'AED ' + Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 0 });
  const fmtNum = (v, d = 0) => Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: d });
  const fmtPct = v => Number(v || 0).toFixed(1) + '%';
  const pad = n => String(n).padStart(2, '0');
  const esc = s => {
    const d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  };
  const toDateInput = d => {
    if (!d) return '';
    const date = new Date(d);
    if (isNaN(date.getTime())) return '';
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  };

  const STAGES = [
    { stage: 'Response', test: () => true },
    { stage: 'Leads', test: c => c.lifecycle === 'New Lead' },
    { stage: 'Hot leads', test: c => c.lifecycle === 'Hot Lead' },
    { stage: 'Quotation', test: c => c.lifecycle === 'Quotation' },
    { stage: 'Follow-up', test: c => ['Appointment', 'Show Up'].includes(c.lifecycle) },
    { stage: 'Customers', test: c => c.lifecycle === 'Customer' },
    { stage: 'Old leads', test: c => c.lifecycle === 'Cold Lead' },
    { stage: 'Bad leads', test: c => ['Bad Lead', 'Lost'].includes(c.lifecycle) },
    { stage: 'Unknown', test: c => !c.lifecycle || c.lifecycle === 'Not set' }
  ];
  const FUNNEL_COLORS = ['#0867c9', '#0a84c9', '#0a9bb0', '#11845b', '#d46b08', '#6b4fd8', '#66758b', '#c43d3d', '#9aa5b5'];

  let filtered = contacts.slice();
  let visibleLimit = 25;
  let funnelView = 'all';

  const els = {
    source: document.getElementById('filterSource'),
    medium: document.getElementById('filterMedium'),
    service: document.getElementById('filterService'),
    lifecycle: document.getElementById('filterLifecycle'),
    from: document.getElementById('filterDateFrom'),
    to: document.getElementById('filterDateTo'),
    apply: document.getElementById('applyFilters'),
    reset: document.getElementById('resetFilters'),
    summary: document.getElementById('filterSummary'),
    hero: document.getElementById('crmHeroKpis'),
    funnel: document.getElementById('lifecycleFunnel'),
    funnelBreakdown: document.getElementById('funnelBreakdown'),
    funnelToggle: document.getElementById('funnelViewToggle'),
    sourceQuality: document.getElementById('sourceQualityRows'),
    serviceQuality: document.getElementById('serviceQualityRows'),
    healthMeter: document.getElementById('healthMeter'),
    healthIssues: document.getElementById('healthIssues'),
    contactRows: document.getElementById('contactRows'),
    loadMore: document.getElementById('loadMoreContacts')
  };

  function populateSelect(sel, items) {
    const current = sel.value;
    const label = sel.dataset.label || sel.id.replace('filter', '').toLowerCase();
    sel.innerHTML = '<option value="">All ' + label + 's</option>';
    (items || []).sort().forEach(item => {
      const opt = document.createElement('option');
      opt.value = item;
      opt.textContent = item;
      sel.appendChild(opt);
    });
    sel.value = current;
  }

  function applyFilters() {
    const s = els.source.value;
    const m = els.medium.value;
    const svc = els.service.value;
    const lc = els.lifecycle.value;
    const from = els.from.value ? new Date(els.from.value) : null;
    const to = els.to.value ? new Date(els.to.value) : null;

    filtered = contacts.filter(c => {
      const d = c.date ? new Date(c.date) : null;
      return (!s || c.source === s) &&
             (!m || c.medium === m) &&
             (!svc || c.service === svc) &&
             (!lc || c.lifecycle === lc) &&
             (!from || (d && d >= from)) &&
             (!to || (d && d <= to));
    });
    visibleLimit = 25;
    render();
  }

  function resetFilters() {
    [els.source, els.medium, els.service, els.lifecycle].forEach(s => s.value = '');
    els.from.value = '';
    els.to.value = '';
    filtered = contacts.slice();
    visibleLimit = 25;
    render();
  }

  function renderHero() {
    if (!els.hero) return;
    const total = filtered.length;
    const june = filtered.filter(c => c.date && c.date.startsWith('2026-06')).length;
    const revenue = filtered.reduce((a, c) => a + Number(c.finalSaleValue || 0), 0);
    const customers = filtered.filter(c => String(c.lifecycle).toLowerCase() === 'customer').length;
    const google = filtered.filter(c => c.source === 'Google Ads').length;
    const meta = filtered.filter(c => c.source === 'Meta Ads').length;

    const values = [
      { label: 'Paid contacts', value: fmtNum(total, 0), sub: `${fmtNum(june, 0)} in June 2026` },
      { label: 'Google Ads contacts', value: fmtNum(google, 0), sub: total ? fmtPct(google / total * 100) + ' of total' : '' },
      { label: 'Meta Ads contacts', value: fmtNum(meta, 0), sub: total ? fmtPct(meta / total * 100) + ' of total' : '' },
      { label: 'Customers', value: fmtNum(customers, 0), sub: total ? fmtPct(customers / total * 100) + ' conversion' : '' },
      { label: 'Final sale value', value: fmtMoney(revenue), sub: `${fmtNum(filtered.filter(c => Number(c.finalSaleValue || 0) > 0).length, 0)} paid invoices` }
    ];

    const kpis = els.hero.querySelectorAll('.kpi');
    values.forEach((v, i) => {
      const kpi = kpis[i];
      if (!kpi) return;
      kpi.querySelector('span').textContent = v.label;
      kpi.querySelector('strong').textContent = v.value;
      const small = kpi.querySelector('small');
      if (small) small.textContent = v.sub || '';
    });
  }

  function computeFunnel(rows) {
    const total = rows.length || 1;
    return STAGES.map(({ stage, test }, idx) => {
      const contacts = rows.filter(test).length;
      return {
        stage,
        contacts,
        rate: rows.length ? (contacts / rows.length * 100) : 0,
        color: FUNNEL_COLORS[idx % FUNNEL_COLORS.length]
      };
    });
  }

  function funnelBarHTML(step, max, sizeClass = '') {
    const w = max ? (step.contacts / max * 100).toFixed(1) : 0;
    return `
      <div class="funnel-bar ${sizeClass}" style="--w:${w}%" title="${step.stage}: ${fmtNum(step.contacts, 0)} contacts (${fmtPct(step.rate)} of total)">
        <div class="meta">
          <span class="name">${step.stage}</span>
          <span class="count">${fmtNum(step.contacts, 0)} <span class="rate">(${fmtPct(step.rate)})</span></span>
        </div>
        <div class="track">
          <div class="fill" style="background:${step.color}"></div>
        </div>
      </div>`;
  }

  function renderFunnel() {
    if (!els.funnel) return;
    const data = computeFunnel(filtered);
    const max = Math.max(...data.map(s => s.contacts || 0), 1);
    els.funnel.innerHTML = data.map(step => funnelBarHTML(step, max)).join('');

    if (!els.funnelBreakdown) return;
    if (funnelView === 'all') {
      els.funnelBreakdown.style.display = 'none';
      els.funnelBreakdown.innerHTML = '';
      return;
    }

    els.funnelBreakdown.style.display = 'grid';
    const dim = funnelView === 'channel' ? 'source' : 'service';
    const groups = groupBy(filtered, dim);
    const keys = Object.keys(groups).sort((a, b) => groups[b].length - groups[a].length);
    const globalMax = Math.max(...keys.map(k => Math.max(...computeFunnel(groups[k]).map(s => s.contacts), 1)), 1);

    els.funnelBreakdown.innerHTML = keys.map(key => {
      const list = groups[key];
      const f = computeFunnel(list);
      return `
        <div class="mini-funnel">
          <h4>${key} <span class="subdue">${fmtNum(list.length, 0)} contacts</span></h4>
          <div class="funnel-bar-list">
            ${f.map(step => funnelBarHTML(step, globalMax, 'compact')).join('')}
          </div>
        </div>`;
    }).join('') || '<p class="empty-state">No data for this breakdown.</p>';
  }

  function groupBy(arr, key) {
    const map = {};
    arr.forEach(c => {
      const k = c[key] || 'Not set';
      if (!map[k]) map[k] = [];
      map[k].push(c);
    });
    return map;
  }

  function renderQuality() {
    const bySource = groupBy(filtered, 'source');
    const sourceRows = Object.keys(bySource).sort().map(source => {
      const list = bySource[source];
      const hotOrQuote = list.filter(c => ['Hot Lead', 'Quotation'].includes(c.lifecycle)).length;
      const customers = list.filter(c => c.lifecycle === 'Customer').length;
      const revenue = list.reduce((a, c) => a + Number(c.finalSaleValue || 0), 0);
      const conversionRate = list.length ? customers / list.length * 100 : 0;
      return `<tr><td>${source}</td><td class="num">${fmtNum(list.length, 0)}</td><td class="num">${fmtNum(hotOrQuote, 0)}</td><td class="num">${fmtNum(customers, 0)}</td><td class="num">${fmtMoney(revenue)}</td><td class="num">${fmtPct(conversionRate)}</td></tr>`;
    }).join('');
    els.sourceQuality.innerHTML = sourceRows || '<tr><td colspan="6" class="empty-state">No data</td></tr>';

    const byService = groupBy(filtered, 'service');
    const serviceRows = Object.keys(byService).sort((a, b) => byService[b].length - byService[a].length).map(service => {
      const list = byService[service];
      const revenue = list.reduce((a, c) => a + Number(c.finalSaleValue || 0), 0);
      const withSale = list.filter(c => Number(c.finalSaleValue || 0) > 0).length;
      const avgSale = withSale ? revenue / withSale : 0;
      const rpc = list.length ? revenue / list.length : 0;
      return `<tr><td>${service}</td><td class="num">${fmtNum(list.length, 0)}</td><td class="num">${fmtMoney(revenue)}</td><td class="num">${fmtMoney(avgSale)}</td><td class="num">${fmtMoney(rpc)}</td></tr>`;
    }).join('');
    els.serviceQuality.innerHTML = serviceRows || '<tr><td colspan="5" class="empty-state">No data</td></tr>';
  }

  function renderHealth() {
    if (!els.healthMeter) return;
    const pct = parseFloat(health.pctComplete) || 0;
    const color = pct >= 80 ? '#11845b' : pct >= 50 ? '#d46b08' : '#c43d3d';
    els.healthMeter.innerHTML = `
      <div class="top">
        <span class="pct">${fmtPct(pct)}</span>
        <span class="subdue">CRM completeness</span>
      </div>
      <div class="track"><div class="fill" style="--w:${pct}%;background:${color}"></div></div>
      <p class="subdue" style="margin-top:10px">${fmtNum(health.total, 0)} contacts · ${fmtNum(health.missingService, 0)} missing service · ${fmtNum(health.missingValue, 0)} missing value</p>
    `;

    const issues = [
      { field: 'Source', missing: health.missingSource || 0, total: health.total || 0 },
      { field: 'Medium', missing: health.missingMedium || 0, total: health.total || 0 },
      { field: 'Lifecycle', missing: health.missingLifecycle || 0, total: health.total || 0 },
      { field: 'Service', missing: health.missingService || 0, total: health.total || 0 },
      { field: 'Quoted value', missing: health.missingValue || 0, total: health.total || 0 },
      { field: 'Duplicate IDs', missing: health.duplicateIds || 0, total: health.total || 0 }
    ];
    els.healthIssues.innerHTML = issues.map(issue => {
      const pct = issue.total ? (issue.missing / issue.total * 100).toFixed(1) : '0.0';
      return `
        <div class="health-issue ${issue.missing ? 'bad' : 'ok'}">
          <span>${issue.field}</span>
          <span class="subdue">${fmtNum(issue.missing, 0)} missing · ${pct}%</span>
        </div>`;
    }).join('');
  }

  function renderContacts() {
    if (!els.contactRows) return;
    const visible = filtered.slice(0, visibleLimit);
    els.contactRows.innerHTML = visible.map(c => `
      <tr>
        <td class="contact-col">${esc(c.contactEntry || '')}</td>
        <td class="contact-col">${esc(c.conversationBrief || '')}</td>
        <td class="contact-col gap-cell">${esc(c.salesComments || 'Not available')}</td>
        <td class="contact-col">${esc(c.notes || '')}</td>
      </tr>
    `).join('') || '<tr><td colspan="4" class="empty-state">No contacts match the current filters.</td></tr>';

    els.loadMore.style.display = visibleLimit >= filtered.length ? 'none' : 'inline-flex';
    els.summary.textContent = `Showing ${fmtNum(visible.length, 0)} of ${fmtNum(filtered.length, 0)} paid contacts${filtered.length !== contacts.length ? ' (filtered)' : ''}.`;
  }

  function render() {
    renderHero();
    renderFunnel();
    renderQuality();
    renderHealth();
    renderContacts();
  }

  function init() {
    if (!data.respondContacts) {
      console.error('respondContacts not found in REPORT_DATA');
      return;
    }
    [els.source, els.medium, els.service, els.lifecycle].forEach(s => {
      s.dataset.label = s.id.replace('filter', '').toLowerCase();
    });
    populateSelect(els.source, options.sources);
    populateSelect(els.medium, options.mediums);
    populateSelect(els.service, options.services);
    populateSelect(els.lifecycle, options.lifecycles);

    if (options.minDate) els.from.min = toDateInput(options.minDate);
    if (options.maxDate) els.from.max = toDateInput(options.maxDate);
    if (options.minDate) els.to.min = toDateInput(options.minDate);
    if (options.maxDate) els.to.max = toDateInput(options.maxDate);

    els.apply.addEventListener('click', applyFilters);
    els.reset.addEventListener('click', resetFilters);
    [els.source, els.medium, els.service, els.lifecycle, els.from, els.to].forEach(el => {
      el.addEventListener('change', applyFilters);
    });
    els.loadMore.addEventListener('click', () => {
      visibleLimit += 25;
      renderContacts();
    });

    if (els.funnelToggle) {
      Array.from(els.funnelToggle.children).forEach(btn => {
        btn.classList.toggle('active', btn.dataset.view === funnelView);
      });
      els.funnelToggle.addEventListener('click', e => {
        if (e.target.tagName !== 'BUTTON') return;
        funnelView = e.target.dataset.view;
        Array.from(els.funnelToggle.children).forEach(btn => {
          btn.classList.toggle('active', btn.dataset.view === funnelView);
        });
        renderFunnel();
      });
    }

    render();
  }

  init();
})();
