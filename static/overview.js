/* Overview figures: sentiment charts (Chart.js) and the stop hotspot map
   (Leaflet). Every figure also has a server-rendered data table, so the page
   still works when a CDN cannot be reached. */
(() => {
  "use strict";

  const data = JSON.parse(document.getElementById("overview-data").textContent);
  const token = (name) =>
    getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const SENTIMENTS = [
    { key: "negative", label: "Negative", color: "--neg" },
    { key: "neutral", label: "Neutral", color: "--neu" },
    { key: "positive", label: "Positive", color: "--pos" },
  ];
  const dayFormat = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });
  const monthFormat = new Intl.DateTimeFormat(undefined, { month: "short", year: "numeric" });

  function showNote(box, text) {
    const note = document.createElement("div");
    note.className = "offline";
    note.textContent = text;
    box.replaceChildren(note);
    const details = box.closest(".card") && box.closest(".card").querySelector("details");
    if (details) details.open = true;
  }

  // ---- Charts -----------------------------------------------------------------

  // Only the visible top segment of a stack gets the rounded data end.
  function isTopSegment(ctx) {
    const { chart, dataIndex, datasetIndex } = ctx;
    for (let d = chart.data.datasets.length - 1; d >= 0; d -= 1) {
      if (chart.isDatasetVisible(d) && (chart.data.datasets[d].data[dataIndex] || 0) > 0) {
        return d === datasetIndex;
      }
    }
    return false;
  }

  function tooltip(unit) {
    return {
      backgroundColor: token("--surface"),
      titleColor: token("--ink-2"),
      bodyColor: token("--ink"),
      borderColor: token("--axis"),
      borderWidth: 1,
      padding: 10,
      usePointStyle: true,
      callbacks: {
        label: (ctx) => ` ${ctx.formattedValue} ${unit(ctx)}`,
        labelColor: (ctx) => ({
          borderColor: ctx.dataset.backgroundColor,
          backgroundColor: ctx.dataset.backgroundColor,
          borderWidth: 2,
        }),
        labelPointStyle: () => ({ pointStyle: "line", rotation: 0 }),
      },
    };
  }

  function options(horizontal, { legend = true, unit = (ctx) => ctx.dataset.label.toLowerCase() } = {}) {
    const valueAxis = {
      stacked: true,
      beginAtZero: true,
      ticks: { precision: 0, color: token("--ink-2") },
      grid: { color: token("--grid") },
      border: { color: token("--axis") },
    };
    const categoryAxis = {
      stacked: true,
      ticks: { color: token("--ink-2"), autoSkip: true, maxRotation: 0 },
      grid: { display: false },
      border: { color: token("--axis") },
    };
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      indexAxis: horizontal ? "y" : "x",
      interaction: { mode: "index", intersect: false, axis: horizontal ? "y" : "x" },
      scales: horizontal ? { x: valueAxis, y: categoryAxis } : { x: categoryAxis, y: valueAxis },
      plugins: {
        legend: {
          display: legend,
          position: "top",
          align: "start",
          labels: {
            color: token("--ink-2"),
            boxWidth: 12,
            boxHeight: 12,
            useBorderRadius: true,
            borderRadius: 3,
            generateLabels: (chart) =>
              Chart.defaults.plugins.legend.labels.generateLabels(chart).map((item) => ({
                ...item, strokeStyle: item.fillStyle, lineWidth: 0,
              })),
          },
        },
        tooltip: tooltip(unit),
      },
    };
  }

  function sentimentDatasets(valuesFor, horizontal) {
    return SENTIMENTS.map((s) => ({
      label: s.label,
      data: valuesFor(s.key),
      backgroundColor: token(s.color),
      borderColor: token("--surface"),
      borderWidth: horizontal ? { right: 2 } : { top: 2 },  // 2px surface gap
      borderSkipped: "start",
      borderRadius: (ctx) => (isTopSegment(ctx) ? 4 : 0),
      maxBarThickness: 24,
    }));
  }

  // Value at the tip of each bar, in the secondary text colour.
  const valueAtTip = {
    id: "valueAtTip",
    afterDatasetsDraw(chart) {
      const { ctx } = chart;
      ctx.save();
      ctx.fillStyle = token("--ink-2");
      ctx.font = `12px ${getComputedStyle(document.body).fontFamily}`;
      ctx.textBaseline = "middle";
      chart.getDatasetMeta(0).data.forEach((bar, i) => {
        const value = chart.data.datasets[0].data[i];
        if (value > 0) ctx.fillText(String(value), bar.x + 6, bar.y);
      });
      ctx.restore();
    },
  };

  function drawTrend(canvas) {
    const t = data.trend;
    const labels = t.periods.map((p) => {
      const d = new Date(`${p}T00:00:00`);
      return t.granularity === "month" ? monthFormat.format(d) : dayFormat.format(d);
    });
    const opts = options(false);
    opts.plugins.tooltip.callbacks.title = (items) =>
      t.granularity === "month" ? labels[items[0].dataIndex] : `Week of ${labels[items[0].dataIndex]}`;
    return new Chart(canvas, {
      type: "bar",
      data: { labels, datasets: sentimentDatasets((key) => t.series[key], false) },
      options: opts,
    });
  }

  function drawRoutes(canvas) {
    const rows = data.byRoute;
    return new Chart(canvas, {
      type: "bar",
      data: {
        labels: rows.map((r) => r.name),
        datasets: sentimentDatasets((key) => rows.map((r) => r[key]), true),
      },
      options: options(true),
    });
  }

  function drawCategories(canvas) {
    const rows = data.byCategory;
    const opts = options(true, { legend: false, unit: () => "negative items" });
    opts.layout = { padding: { right: 28 } };
    return new Chart(canvas, {
      type: "bar",
      data: {
        labels: rows.map((r) => r.label),
        datasets: [{
          label: "Negative items",
          data: rows.map((r) => r.negative),
          backgroundColor: token("--neg"),
          borderSkipped: "start",
          borderRadius: 4,
          maxBarThickness: 24,
        }],
      },
      options: opts,
      plugins: [valueAtTip],
    });
  }

  const figures = [
    { id: "trend-chart", draw: drawTrend, empty: () => data.trend.periods.length === 0 },
    { id: "route-chart", draw: drawRoutes, empty: () => data.byRoute.length === 0 },
    { id: "category-chart", draw: drawCategories, empty: () => data.byCategory.length === 0 },
  ];
  let charts = [];

  function drawCharts() {
    charts.forEach((c) => c.destroy());
    charts = [];
    figures.forEach((f) => {
      const canvas = document.getElementById(f.id);
      if (!canvas) return;
      if (f.empty()) {
        showNote(canvas.parentElement, "No feedback matches these filters.");
      } else if (!window.Chart) {
        showNote(canvas.parentElement,
          "The chart library could not load (no internet connection?). The data table below has the same values.");
      } else {
        charts.push(f.draw(canvas));
      }
    });
  }

  // ---- Map ------------------------------------------------------------------------

  const markers = [];

  function tooltipFor(stop) {
    const box = document.createElement("div");
    const value = document.createElement("strong");
    value.textContent = `${stop.negative} negative`;
    box.append(value, ` of ${stop.total} item${stop.total === 1 ? "" : "s"}`,
      document.createElement("br"), stop.stop);
    return box;
  }

  function markerStyle(stop) {
    return { color: token("--surface"), fillColor: token(stop.negative ? "--neg" : "--neu") };
  }

  function drawMap() {
    const el = document.getElementById("map");
    if (!window.L) {
      showNote(el, "The map could not load (no internet connection?). The stops table below has the same data.");
      return;
    }
    const map = L.map(el, { scrollWheelZoom: false });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);
    const max = Math.max(1, ...data.stops.map((s) => s.negative));
    const filters = new URLSearchParams(window.location.search);
    data.stops.forEach((stop) => {
      // Stations without feedback stay small and faint so hotspots stand out.
      const radius = stop.negative ? 6 + 12 * Math.sqrt(stop.negative / max) : stop.total ? 5 : 4;
      const marker = L.circleMarker([stop.lat, stop.lon], {
        radius, weight: 2, fillOpacity: stop.total ? 0.9 : 0.55, ...markerStyle(stop),
      });
      marker.bindTooltip(tooltipFor(stop), { direction: "top", offset: [0, -radius] });
      marker.on("click", () => {
        const query = new URLSearchParams(filters);
        query.set("stop", stop.stop);
        window.location.href = `/feedback?${query}`;
      });
      marker.addTo(map);
      markers.push({ marker, stop });
    });
    // Zoom to the stations that have feedback; show the whole network otherwise.
    const withFeedback = data.stops.filter((s) => s.total > 0);
    const focus = withFeedback.length >= 2 ? withFeedback : data.stops;
    if (focus.length) {
      map.fitBounds(focus.map((s) => [s.lat, s.lon]), { padding: [30, 30] });
    } else {
      map.setView([45.4215, -75.6972], 12);
    }
  }

  drawCharts();
  drawMap();

  // Dark mode uses its own colour steps, so redraw when the scheme changes.
  const scheme = window.matchMedia("(prefers-color-scheme: dark)");
  if (scheme.addEventListener) {
    scheme.addEventListener("change", () => {
      if (window.Chart) drawCharts();
      markers.forEach(({ marker, stop }) => marker.setStyle(markerStyle(stop)));
    });
  }
})();
