let activeRespondFilter = 'All';
    let respondFiltersReady = false;

    function setText(id, value) {
      const el = document.getElementById(id);
      if (el) el.textContent = value;
    }

    function renderRows(tbodyId, rows) {
      const tbody = document.getElementById(tbodyId);
      if (!tbody) return;
      tbody.innerHTML = rows.length
        ? rows.map(row => `<tr>${row.map((cell, idx) => `<td class="${idx && /^AED |^[\d,.]+$|^[\d,.]+%/.test(String(cell)) ? 'num' : ''}">${cell}</td>`).join('')}</tr>`).join('')
        : '<tr><td colspan="4">No contacts in this filter</td></tr>';
    }

    function renderFunnelSteps(funnel) {
      const container = document.querySelector('#funnel .funnel');
      if (!container || !funnel || !funnel.length) return;
      container.innerHTML = funnel.map((step, i) => `
        <div class="funnel-step" id="funnelStep${i + 1}" style="--w:${Math.max(18, 100 - i * 13)}%">
          <span>${escapeHtml(step.label)}</span>
          <strong>${escapeHtml(step.value)}</strong>
          <small>${escapeHtml(step.note)}</small>
        </div>
      `).join('');
    }

    function updateRespond(filterName = activeRespondFilter) {
      const filters = REPORT_DATA.respondFilters || {};
      const data = filters[filterName] || filters.All || {
        label: filterName,
        total: 0,
        hotOrQuote: 0,
        customerLike: 0,
        sources: [],
        lifecycle: [],
        services: [],
        sourceServices: [],
        sourceMediums: []
      };
      activeRespondFilter = data.label || filterName;
      document.querySelectorAll('[data-respond-channel]').forEach(button => {
        button.classList.toggle('active', button.dataset.respondChannel === activeRespondFilter);
      });
      const hotRate = data.total ? data.hotOrQuote / data.total * 100 : 0;
      const customerRate = data.total ? data.customerLike / data.total * 100 : 0;
      const topService = (data.services || [])[0] || {};
      setText('respondPaidContacts', num(data.total));
      setText('respondPaidNote', activeRespondFilter === 'All' ? 'All paid contacts' : `${activeRespondFilter} paid contacts`);
      setText('respondHotQuote', num(data.hotOrQuote));
      setText('respondHotQuoteNote', `${pct(hotRate)} of contacts`);
      setText('respondCustomerLike', num(data.customerLike));
      setText('respondCustomerLikeNote', `${pct(customerRate)} of contacts`);
      setText('respondTopService', topService.service || 'N/A');
      setText('respondTopServiceNote', `${num(topService.contacts || 0)} contacts`);

      renderRows('respondSourceRows', (data.sources || []).map(row => [
        escapeHtml(row.source),
        num(row.contacts),
        money(row.quotedValue),
        money(row.revenue)
      ]));
      renderRows('respondLifecycleRows', (data.lifecycle || []).map(row => [
        escapeHtml(row.lifecycle),
        num(row.contacts)
      ]));
      renderRows('respondServiceRows', (data.services || []).map(row => [
        escapeHtml(row.service),
        num(row.contacts),
        money(row.quotedValue),
        money(row.revenue)
      ]));
      renderRows('respondSourceServiceRows', (data.sourceServices || []).map(row => [
        escapeHtml(row.source),
        escapeHtml(row.service),
        num(row.contacts)
      ]));
      renderRows('respondSourceMediumRows', (data.sourceMediums || []).map(row => [
        escapeHtml(row.source),
        escapeHtml(row.medium),
        num(row.contacts)
      ]));
      drawBarChart('respondLifecycleChart', {
        labels: (data.lifecycle || []).map(row => row.lifecycle),
        values: (data.lifecycle || []).map(row => row.contacts),
        horizontal: true,
        color: COLORS.green,
        title: `${activeRespondFilter} contacts by lifecycle`
      });
      renderFunnelSteps(data.funnel);
    }

    function initRespondFilters() {
      if (respondFiltersReady) return;
      document.querySelectorAll('[data-respond-channel]').forEach(button => {
        button.addEventListener('click', () => updateRespond(button.dataset.respondChannel));
      });
      respondFiltersReady = true;
      updateRespond('All');
    }

function renderRespond() {
  updateRespond(activeRespondFilter);
}
window.addEventListener('resize', () => window.requestAnimationFrame(renderRespond));
renderRespond();
initRespondFilters();
