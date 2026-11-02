/* ==========================================================================
   轻量图表库（纯 SVG / DOM，无第三方依赖）
   提供：柱状图 barChart / 环形图 donutChart / 折线面图 areaChart / 条形图 hbarChart
   ========================================================================== */
(function (global) {
  'use strict';

  var NS = 'http://www.w3.org/2000/svg';
  var registry = new Map();
  var uid = 0;

  function svgEl(name, attrs) {
    var node = document.createElementNS(NS, name);
    if (attrs) {
      Object.keys(attrs).forEach(function (key) {
        node.setAttribute(key, attrs[key]);
      });
    }
    return node;
  }

  function sizeOf(container) {
    var rect = container.getBoundingClientRect();
    var w = rect.width || container.clientWidth || 320;
    var h = rect.height || container.clientHeight || 200;
    return { w: Math.max(w, 200), h: Math.max(h, 120) };
  }

  function emptyState(text) {
    var div = document.createElement('div');
    div.className = 'chart-empty';
    div.textContent = text || '本月还没有数据';
    return div;
  }

  function fmt(value) {
    var rounded = Math.round(value * 10) / 10;
    return String(rounded);
  }

  // 整数刻度：避免出现 3.3 / 1.7 这类不友好的坐标
  function axisTicks(maxValue) {
    var value = Math.max(maxValue, 1);
    var segments = 5;
    var rawStep = value / segments;
    var power = Math.pow(10, Math.floor(Math.log10(rawStep || 1)));
    var candidates = [1, 2, 2.5, 5, 10].map(function (m) { return m * power; });
    var step = candidates[candidates.length - 1];
    for (var i = 0; i < candidates.length; i++) {
      if (candidates[i] >= rawStep) { step = candidates[i]; break; }
    }
    if (step < 1) step = 1;
    if (value <= 8) step = 1;
    var count = Math.max(1, Math.ceil(value / step));
    if (count > 6) {
      step = Math.ceil(value / 5);
      if (step < 1) step = 1;
      count = Math.ceil(value / step);
    }
    var ticks = [];
    for (var t = 0; t <= count; t++) ticks.push(step * t);
    return { top: step * count, ticks: ticks };
  }

  // ------------------------------------------------------------- 悬浮提示
  function tipNode() {
    return document.getElementById('chartTip');
  }

  function showTip(html, clientX, clientY) {
    var node = tipNode();
    if (!node) return;
    node.innerHTML = html;
    node.hidden = false;
    var rect = node.getBoundingClientRect();
    var left = clientX + 14;
    var top = clientY - rect.height - 12;
    if (left + rect.width > window.innerWidth - 12) left = clientX - rect.width - 14;
    if (top < 8) top = clientY + 18;
    node.style.left = Math.round(left) + 'px';
    node.style.top = Math.round(top) + 'px';
  }

  function hideTip() {
    var node = tipNode();
    if (node) node.hidden = true;
  }

  // ------------------------------------------------------------- 柱状图
  function barChart(container, items, opts) {
    opts = opts || {};
    registry.set(container, function () {
      var size = sizeOf(container);
      var w = size.w;
      var h = size.h;
      container.innerHTML = '';

      if (!items || !items.length) {
        container.appendChild(emptyState(opts.emptyText));
        return;
      }

      var pad = { top: 16, right: 10, bottom: 26, left: 32 };
      var innerW = Math.max(w - pad.left - pad.right, 10);
      var innerH = Math.max(h - pad.top - pad.bottom, 10);
      var maxValue = Math.max.apply(null, items.map(function (d) { return d.value || 0; }));
      var axis = axisTicks(maxValue);
      var top = axis.top;
      var step = innerW / items.length;
      var barW = Math.max(Math.min(step * (opts.barRatio || 0.62), 26), 3);

      var svg = svgEl('svg', {
        class: 'chart-svg',
        width: w,
        height: h,
        viewBox: '0 0 ' + w + ' ' + h
      });

      var gid = 'barGrad' + (++uid);
      var defs = svgEl('defs');
      var grad = svgEl('linearGradient', { id: gid, x1: '0', y1: '0', x2: '0', y2: '1' });
      grad.appendChild(svgEl('stop', { offset: '0%', 'stop-color': '#6578f6' }));
      grad.appendChild(svgEl('stop', { offset: '100%', 'stop-color': '#4567f2' }));
      defs.appendChild(grad);
      svg.appendChild(defs);

      axis.ticks.forEach(function (tick) {
        var y = pad.top + innerH - (tick / top) * innerH;
        svg.appendChild(svgEl('line', {
          x1: pad.left, y1: y, x2: pad.left + innerW, y2: y,
          stroke: '#eef1f7', 'stroke-width': 1
        }));
        var label = svgEl('text', {
          x: pad.left - 8, y: y + 3.5,
          'text-anchor': 'end', fill: '#a3acbc', 'font-size': 10
        });
        label.textContent = fmt(tick);
        svg.appendChild(label);
      });

      var stepLabel = Math.max(1, Math.ceil(items.length / Math.max(1, Math.floor(innerW / 30))));

      items.forEach(function (item, index) {
        var cx = pad.left + step * index + step / 2;
        var value = item.value || 0;
        var doneValue = item.done || 0;
        var barH = top ? (value / top) * innerH : 0;
        var doneH = top ? (doneValue / top) * innerH : 0;
        var x = cx - barW / 2;
        var baseY = pad.top + innerH;

        if (value > 0) {
          svg.appendChild(svgEl('rect', {
            x: x, y: baseY - barH, width: barW, height: barH,
            rx: Math.min(4, barW / 2), fill: opts.baseColor || '#e9edfb'
          }));
        } else {
          svg.appendChild(svgEl('rect', {
            x: x, y: baseY - 2, width: barW, height: 2,
            rx: 1, fill: '#eef1f7'
          }));
        }

        if (doneH > 0.5) {
          svg.appendChild(svgEl('rect', {
            x: x, y: baseY - doneH, width: barW, height: doneH,
            rx: Math.min(4, barW / 2), fill: 'url(#' + gid + ')'
          }));
        }

        if (index % stepLabel === 0 || index === items.length - 1) {
          var text = svgEl('text', {
            x: cx, y: pad.top + innerH + 17,
            'text-anchor': 'middle', fill: '#a3acbc', 'font-size': 10
          });
          text.textContent = item.label;
          svg.appendChild(text);
        }

        var hot = svgEl('rect', {
          x: pad.left + step * index, y: pad.top,
          width: step, height: innerH, fill: 'transparent'
        });
        hot.style.cursor = 'default';
        hot.addEventListener('mousemove', function (event) {
          var lines = [item.tipTitle || ('第 ' + item.label + ' 日')];
          lines.push('安排 ' + value + ' 项');
          if (opts.showDone) lines.push('完成 ' + doneValue + ' 项');
          showTip(lines.join('<br>'), event.clientX, event.clientY);
        });
        hot.addEventListener('mouseleave', hideTip);
        svg.appendChild(hot);
      });

      container.appendChild(svg);
    });
  }

  // ------------------------------------------------------------- 折线面图
  function smoothPath(points) {
    if (!points.length) return '';
    var d = 'M ' + points[0].x + ' ' + points[0].y;
    for (var i = 0; i < points.length - 1; i++) {
      var p0 = points[i - 1] || points[i];
      var p1 = points[i];
      var p2 = points[i + 1];
      var p3 = points[i + 2] || p2;
      var c1x = p1.x + (p2.x - p0.x) / 6;
      var c1y = p1.y + (p2.y - p0.y) / 6;
      var c2x = p2.x - (p3.x - p1.x) / 6;
      var c2y = p2.y - (p3.y - p1.y) / 6;
      d += ' C ' + c1x + ' ' + c1y + ', ' + c2x + ' ' + c2y + ', ' + p2.x + ' ' + p2.y;
    }
    return d;
  }

  function areaChart(container, points, opts) {
    opts = opts || {};
    registry.set(container, function () {
      var size = sizeOf(container);
      var w = size.w;
      var h = size.h;
      container.innerHTML = '';

      if (!points || !points.length || !points[points.length - 1].planned) {
        container.appendChild(emptyState(opts.emptyText));
        return;
      }

      var pad = { top: 16, right: 12, bottom: 24, left: 32 };
      var innerW = Math.max(w - pad.left - pad.right, 10);
      var innerH = Math.max(h - pad.top - pad.bottom, 10);
      var maxPlanned = Math.max.apply(null, points.map(function (p) { return p.planned || 0; }));
      var axis = axisTicks(maxPlanned);
      var top = axis.top;
      var step = points.length > 1 ? innerW / (points.length - 1) : 0;

      var svg = svgEl('svg', { class: 'chart-svg', width: w, height: h, viewBox: '0 0 ' + w + ' ' + h });
      var gid = 'areaGrad' + (++uid);
      var defs = svgEl('defs');
      var grad = svgEl('linearGradient', { id: gid, x1: '0', y1: '0', x2: '0', y2: '1' });
      grad.appendChild(svgEl('stop', { offset: '0%', 'stop-color': '#4567f2', 'stop-opacity': '0.26' }));
      grad.appendChild(svgEl('stop', { offset: '100%', 'stop-color': '#4567f2', 'stop-opacity': '0' }));
      defs.appendChild(grad);
      svg.appendChild(defs);

      axis.ticks.forEach(function (tick) {
        var y = pad.top + innerH - (tick / top) * innerH;
        svg.appendChild(svgEl('line', {
          x1: pad.left, y1: y, x2: pad.left + innerW, y2: y,
          stroke: '#eef1f7', 'stroke-width': 1
        }));
        var label = svgEl('text', {
          x: pad.left - 8, y: y + 3.5,
          'text-anchor': 'end', fill: '#a3acbc', 'font-size': 10
        });
        label.textContent = fmt(tick);
        svg.appendChild(label);
      });

      function toPoints(key) {
        return points.map(function (item, index) {
          var x = pad.left + step * index;
          var y = pad.top + innerH - ((item[key] || 0) / top) * innerH;
          return { x: x, y: y };
        });
      }

      var plannedPts = toPoints('planned');
      var donePts = toPoints('done');

      svg.appendChild(svgEl('path', {
        d: smoothPath(plannedPts),
        fill: 'none', stroke: '#c8d1f4', 'stroke-width': 1.6,
        'stroke-dasharray': '5 5', 'stroke-linecap': 'round'
      }));

      var area = smoothPath(donePts);
      if (area) {
        var closing = ' L ' + donePts[donePts.length - 1].x + ' ' + (pad.top + innerH) +
          ' L ' + donePts[0].x + ' ' + (pad.top + innerH) + ' Z';
        svg.appendChild(svgEl('path', { d: area + closing, fill: 'url(#' + gid + ')', stroke: 'none' }));
      }

      svg.appendChild(svgEl('path', {
        d: smoothPath(donePts),
        fill: 'none', stroke: '#4567f2', 'stroke-width': 2.4,
        'stroke-linecap': 'round', 'stroke-linejoin': 'round'
      }));

      var stepLabel = Math.max(1, Math.ceil(points.length / Math.max(1, Math.floor(innerW / 34))));
      points.forEach(function (item, index) {
        if (index % stepLabel === 0 || index === points.length - 1) {
          var text = svgEl('text', {
            x: pad.left + step * index, y: pad.top + innerH + 16,
            'text-anchor': 'middle', fill: '#a3acbc', 'font-size': 10
          });
          text.textContent = item.day;
          svg.appendChild(text);
        }
        if (index % Math.max(1, Math.floor(points.length / 8)) === 0 || index === points.length - 1) {
          svg.appendChild(svgEl('circle', {
            cx: donePts[index].x, cy: donePts[index].y, r: 2.6,
            fill: '#fff', stroke: '#4567f2', 'stroke-width': 1.8
          }));
        }

        var hot = svgEl('rect', {
          x: pad.left + step * index - step / 2, y: pad.top,
          width: Math.max(step, 6), height: innerH, fill: 'transparent'
        });
        hot.addEventListener('mousemove', function (event) {
          showTip(
            '第 ' + item.day + ' 日<br>累计安排 ' + item.planned + ' 项<br>累计完成 ' + item.done + ' 项',
            event.clientX, event.clientY
          );
        });
        hot.addEventListener('mouseleave', hideTip);
        svg.appendChild(hot);
      });

      container.appendChild(svg);
    });
  }

  // ------------------------------------------------------------- 环形图
  function donutChart(container, items, opts) {
    opts = opts || {};
    registry.set(container, function () {
      var size = sizeOf(container);
      container.innerHTML = '';

      var total = items.reduce(function (sum, item) { return sum + (item.value || 0); }, 0);
      if (!items.length || !total) {
        container.appendChild(emptyState(opts.emptyText));
        return;
      }

      var outer = Math.max(120, Math.min(size.h, size.w * 0.52));
      var thickness = Math.max(14, outer * 0.14);
      var radius = outer / 2 - thickness / 2 - 2;
      var center = outer / 2;
      var circumference = 2 * Math.PI * radius;

      var wrap = document.createElement('div');
      wrap.className = 'donut-wrap';

      var svg = svgEl('svg', {
        class: 'donut-svg', width: outer, height: outer,
        viewBox: '0 0 ' + outer + ' ' + outer
      });

      svg.appendChild(svgEl('circle', {
        cx: center, cy: center, r: radius,
        fill: 'none', stroke: '#f2f5fa', 'stroke-width': thickness
      }));

      var offset = 0;
      items.forEach(function (item) {
        var fraction = (item.value || 0) / total;
        var length = Math.max(fraction * circumference - 2, 1.2);
        var arc = svgEl('circle', {
          cx: center, cy: center, r: radius,
          fill: 'none', stroke: item.color || '#4567f2', 'stroke-width': thickness,
          'stroke-dasharray': length + ' ' + (circumference - length),
          'stroke-dashoffset': -offset,
          transform: 'rotate(-90 ' + center + ' ' + center + ')',
          'stroke-linecap': 'butt'
        });
        arc.style.transition = 'stroke-dasharray .5s ease';
        svg.appendChild(arc);

        var shareText = Math.round(fraction * 100) + '%';
        var hot = svgEl('circle', {
          cx: center, cy: center, r: radius,
          fill: 'none', stroke: 'transparent', 'stroke-width': thickness + 6,
          'stroke-dasharray': length + ' ' + (circumference - length),
          'stroke-dashoffset': -offset,
          transform: 'rotate(-90 ' + center + ' ' + center + ')'
        });
        hot.addEventListener('mousemove', function (event) {
          showTip(item.name + '<br>共 ' + item.value + ' 项 · 占比 ' + shareText, event.clientX, event.clientY);
        });
        hot.addEventListener('mouseleave', hideTip);
        svg.appendChild(hot);

        offset += fraction * circumference;
      });

      var centerText = svgEl('text', {
        x: center, y: center - 2, 'text-anchor': 'middle',
        fill: '#172033', 'font-size': Math.round(outer * 0.17), 'font-weight': '700'
      });
      centerText.textContent = opts.centerValue != null ? opts.centerValue : total;
      svg.appendChild(centerText);

      var centerLabel = svgEl('text', {
        x: center, y: center + Math.round(outer * 0.12), 'text-anchor': 'middle',
        fill: '#98a3b7', 'font-size': 11
      });
      centerLabel.textContent = opts.centerLabel || '项日程';
      svg.appendChild(centerLabel);

      wrap.appendChild(svg);

      var legend = document.createElement('ul');
      legend.className = 'donut-legend';
      items.forEach(function (item) {
        var li = document.createElement('li');
        var dot = document.createElement('i');
        dot.style.background = item.color || '#4567f2';
        var name = document.createElement('span');
        name.textContent = item.name;
        name.style.color = '#4b5670';
        var count = document.createElement('b');
        count.textContent = item.value;
        var pct = document.createElement('span');
        pct.textContent = Math.round((item.value / total) * 100) + '%';
        li.appendChild(dot);
        li.appendChild(name);
        li.appendChild(count);
        li.appendChild(pct);
        legend.appendChild(li);
      });
      wrap.appendChild(legend);

      container.appendChild(wrap);
    });
  }

  // ------------------------------------------------------------- 条形图
  function hbarChart(container, items, opts) {
    opts = opts || {};
    registry.set(container, function () {
      container.innerHTML = '';
      if (!items || !items.length || !items.some(function (i) { return i.value > 0; })) {
        container.appendChild(emptyState(opts.emptyText));
        return;
      }

      var max = Math.max.apply(null, items.map(function (item) { return item.value || 0; })) || 1;
      var list = document.createElement('div');
      list.className = 'hbar-list';

      items.forEach(function (item) {
        var row = document.createElement('div');
        row.className = 'hbar-row';

        var top = document.createElement('div');
        top.className = 'hbar-top';
        var label = document.createElement('span');
        label.textContent = item.name;
        var value = document.createElement('b');
        value.textContent = item.value + ' 项';
        top.appendChild(label);
        top.appendChild(value);

        var track = document.createElement('div');
        track.className = 'hbar-track';
        var fill = document.createElement('div');
        fill.className = 'hbar-fill';
        fill.style.width = '0%';
        fill.style.background = item.color || 'linear-gradient(90deg,#4567f2,#8b5cf6)';
        track.appendChild(fill);

        row.appendChild(top);
        row.appendChild(track);
        list.appendChild(row);

        requestAnimationFrame(function () {
          fill.style.width = Math.max((item.value / max) * 100, item.value ? 4 : 0) + '%';
        });

        row.addEventListener('mousemove', function (event) {
          var text = item.name + '<br>共 ' + item.value + ' 项';
          if (item.done != null) text += '<br>完成 ' + item.done + ' 项';
          showTip(text, event.clientX, event.clientY);
        });
        row.addEventListener('mouseleave', hideTip);
      });

      container.appendChild(list);
    });
  }

  // ------------------------------------------------------------- 尺寸自适应
  var resizeTimer = null;
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      registry.forEach(function (render) {
        try { render(); } catch (error) { /* 忽略重绘异常 */ }
      });
    }, 180);
  });

  global.MiniCharts = {
    barChart: function (container, items, opts) { barChart(container, items, opts); if (container) registry.get(container)(); },
    donutChart: function (container, items, opts) { donutChart(container, items, opts); if (container) registry.get(container)(); },
    areaChart: function (container, points, opts) { areaChart(container, points, opts); if (container) registry.get(container)(); },
    hbarChart: function (container, items, opts) { hbarChart(container, items, opts); if (container) registry.get(container)(); },
    hideTip: hideTip
  };
})(window);
