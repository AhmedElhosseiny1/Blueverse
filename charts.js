const tooltip = document.getElementById('tooltip');
    const money = value => 'AED ' + Number(value || 0).toLocaleString(undefined, {maximumFractionDigits: 0});
    const num = (value, digits = 0) => Number(value || 0).toLocaleString(undefined, {maximumFractionDigits: digits});
    const pct = value => Number(value || 0).toFixed(1) + '%';
    const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
    }[char]));

    function showTip(event, text) {
      tooltip.textContent = text;
      tooltip.style.left = event.clientX + 'px';
      tooltip.style.top = event.clientY + 'px';
      tooltip.style.opacity = '1';
    }
    function hideTip() { tooltip.style.opacity = '0'; }

    function svgEl(name, attrs = {}, parent) {
      const el = document.createElementNS('http://www.w3.org/2000/svg', name);
      for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
      if (parent) parent.appendChild(el);
      return el;
    }

    function clearSvg(id, height = 300) {
      const svg = document.getElementById(id);
      svg.innerHTML = '';
      const width = Math.max(svg.clientWidth || 700, 420);
      svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
      return {svg, width, height};
    }

    function drawAxes(svg, width, height, pad, maxY, labels) {
      const plotW = width - pad.left - pad.right;
      const plotH = height - pad.top - pad.bottom;
      for (let i = 0; i <= 4; i++) {
        const y = pad.top + plotH * i / 4;
        svgEl('line', {x1: pad.left, y1: y, x2: width - pad.right, y2: y, stroke: COLORS.line, 'stroke-width': 1}, svg);
        const value = maxY * (1 - i / 4);
        svgEl('text', {x: pad.left - 8, y: y + 4, 'text-anchor': 'end', fill: COLORS.muted, 'font-size': 11}, svg).textContent = num(value);
      }
      labels.forEach((label, i) => {
        if (labels.length > 12 && i % Math.ceil(labels.length / 8) !== 0) return;
        const x = pad.left + plotW * (labels.length <= 1 ? 0.5 : i / (labels.length - 1));
        svgEl('text', {x, y: height - 12, 'text-anchor': 'middle', fill: COLORS.muted, 'font-size': 10}, svg).textContent = String(label).slice(5);
      });
    }

    function drawLineChart(id, config) {
      const {svg, width, height} = clearSvg(id, config.height || 360);
      const pad = {left: 58, right: 24, top: 24, bottom: 46};
      const labels = config.labels || [];
      const datasets = (config.datasets || []).filter(ds => ds.data && ds.data.length);
      const allValues = datasets.flatMap(ds => ds.data.map(v => Number(v || 0))).filter(Number.isFinite);
      const maxY = Math.max(1, ...allValues) * 1.12;
      const plotW = width - pad.left - pad.right;
      const plotH = height - pad.top - pad.bottom;
      drawAxes(svg, width, height, pad, maxY, labels);
      datasets.forEach((ds, dsIndex) => {
        const points = ds.data.map((v, i) => {
          const x = pad.left + plotW * (labels.length <= 1 ? 0.5 : i / (labels.length - 1));
          const y = pad.top + plotH * (1 - Number(v || 0) / maxY);
          return [x, y, v, labels[i]];
        });
        const path = points.map((p, i) => `${i ? 'L' : 'M'}${p[0]},${p[1]}`).join(' ');
        svgEl('path', {d: path, fill: 'none', stroke: ds.color, 'stroke-width': 3, 'stroke-linejoin': 'round', 'stroke-linecap': 'round'}, svg);
        points.forEach(p => {
          const dot = svgEl('circle', {cx: p[0], cy: p[1], r: 4, fill: ds.color, stroke: '#fff', 'stroke-width': 2}, svg);
          dot.addEventListener('mousemove', ev => showTip(ev, `${ds.label} · ${p[3]}: ${num(p[2], 2)}`));
          dot.addEventListener('mouseleave', hideTip);
        });
        const lx = pad.left + dsIndex * 160;
        svgEl('circle', {cx: lx, cy: 12, r: 5, fill: ds.color}, svg);
        svgEl('text', {x: lx + 10, y: 16, fill: COLORS.muted, 'font-size': 12, 'font-weight': 700}, svg).textContent = ds.label;
      });
    }

    function drawBarChart(id, config) {
      const {svg, width, height} = clearSvg(id, config.height || 320);
      const horizontal = !!config.horizontal;
      const labels = config.labels || [];
      const values = (config.values || []).map(v => Number(v || 0));
      const max = Math.max(1, ...values) * 1.12;
      const pad = horizontal ? {left: 170, right: 32, top: 28, bottom: 34} : {left: 54, right: 22, top: 28, bottom: 70};
      const plotW = width - pad.left - pad.right;
      const plotH = height - pad.top - pad.bottom;
      svgEl('text', {x: pad.left, y: 16, fill: COLORS.muted, 'font-size': 12, 'font-weight': 800}, svg).textContent = config.title || '';
      if (horizontal) {
        const barH = Math.max(12, Math.min(26, plotH / Math.max(1, labels.length) - 6));
        labels.forEach((label, i) => {
          const y = pad.top + i * (plotH / Math.max(1, labels.length)) + 4;
          const w = plotW * values[i] / max;
          svgEl('text', {x: pad.left - 10, y: y + barH * .75, 'text-anchor': 'end', fill: COLORS.muted, 'font-size': 11}, svg).textContent = String(label).slice(0, 24);
          const rect = svgEl('rect', {x: pad.left, y, width: Math.max(2, w), height: barH, rx: 4, fill: config.color || COLORS.blue}, svg);
          rect.addEventListener('mousemove', ev => showTip(ev, `${label}: ${num(values[i], 2)}`));
          rect.addEventListener('mouseleave', hideTip);
        });
      } else {
        const gap = 8;
        const barW = Math.max(12, (plotW - gap * (labels.length - 1)) / Math.max(1, labels.length));
        values.forEach((value, i) => {
          const h = plotH * value / max;
          const x = pad.left + i * (barW + gap);
          const y = pad.top + plotH - h;
          svgEl('rect', {x, y, width: barW, height: Math.max(2, h), rx: 4, fill: config.color || COLORS.blue}, svg)
            .addEventListener('mousemove', ev => showTip(ev, `${labels[i]}: ${num(value, 2)}`));
          svgEl('text', {x: x + barW / 2, y: height - 18, 'text-anchor': 'middle', fill: COLORS.muted, 'font-size': 10, transform: `rotate(-28 ${x + barW / 2} ${height - 18})`}, svg).textContent = String(labels[i]).slice(0, 18);
        });
        for (let i = 0; i <= 4; i++) {
          const y = pad.top + plotH * i / 4;
          svgEl('line', {x1: pad.left, y1: y, x2: width - pad.right, y2: y, stroke: COLORS.line, 'stroke-width': 1}, svg);
        }
      }
    }

    function drawGroupedBars(id, config) {
      const {svg, width, height} = clearSvg(id, config.height || 330);
      const labels = config.labels || [];
      const datasets = config.datasets || [];
      const all = datasets.flatMap(ds => ds.values.map(v => Number(v || 0)));
      const max = Math.max(1, ...all) * 1.14;
      const pad = {left: 56, right: 26, top: 28, bottom: 72};
      const plotW = width - pad.left - pad.right;
      const plotH = height - pad.top - pad.bottom;
      const groupW = plotW / Math.max(1, labels.length);
      const barW = Math.max(8, (groupW - 12) / Math.max(1, datasets.length));
      for (let i = 0; i <= 4; i++) {
        const y = pad.top + plotH * i / 4;
        svgEl('line', {x1: pad.left, y1: y, x2: width - pad.right, y2: y, stroke: COLORS.line, 'stroke-width': 1}, svg);
      }
      datasets.forEach((ds, di) => {
        labels.forEach((label, i) => {
          const value = Number(ds.values[i] || 0);
          const h = plotH * value / max;
          const x = pad.left + i * groupW + 6 + di * barW;
          const y = pad.top + plotH - h;
          const rect = svgEl('rect', {x, y, width: barW - 2, height: Math.max(2, h), rx: 4, fill: ds.color}, svg);
          rect.addEventListener('mousemove', ev => showTip(ev, `${ds.label} · ${label}: ${num(value, 2)}`));
          rect.addEventListener('mouseleave', hideTip);
        });
        const lx = pad.left + di * 140;
        svgEl('rect', {x: lx, y: 10, width: 10, height: 10, rx: 3, fill: ds.color}, svg);
        svgEl('text', {x: lx + 15, y: 19, fill: COLORS.muted, 'font-size': 12, 'font-weight': 700}, svg).textContent = ds.label;
      });
      labels.forEach((label, i) => {
        const x = pad.left + i * groupW + groupW / 2;
        svgEl('text', {x, y: height - 18, 'text-anchor': 'middle', fill: COLORS.muted, 'font-size': 10, transform: `rotate(-28 ${x} ${height - 18})`}, svg).textContent = String(label).slice(0, 18);
      });
    }

    function drawHeatmap() {
      const box = document.getElementById('conversionHeatmap');
      const data = REPORT_DATA.heatmap.conversions;
      const max = Math.max(1, ...data.flat().map(Number));
      box.innerHTML = '';
      REPORT_DATA.heatmap.days.forEach((day, y) => {
        const row = document.createElement('div');
        row.className = 'heat-row';
        row.innerHTML = `<span class="heat-label">${day}</span>`;
        data[y].forEach((value, hour) => {
          const cell = document.createElement('span');
          cell.className = 'heat-cell';
          const alpha = .08 + .86 * Number(value || 0) / max;
          cell.style.background = `rgba(8,103,201,${alpha})`;
          cell.addEventListener('mousemove', ev => showTip(ev, `${day} ${hour}:00 · Conversions: ${num(value, 1)}`));
          cell.addEventListener('mouseleave', hideTip);
          row.appendChild(cell);
        });
        box.appendChild(row);
      });
      const axis = document.createElement('div');
      axis.className = 'heat-axis';
      axis.innerHTML = '<span></span>' + REPORT_DATA.heatmap.hours.map(h => `<span>${h % 3 === 0 ? h : ''}</span>`).join('');
      box.appendChild(axis);
    }
