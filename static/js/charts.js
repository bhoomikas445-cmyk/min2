/**
 * PALIMPSEST Chart.js Controller
 * Visualizations for memory distribution, token budgets, and benchmark comparisons.
 */

// Category Distribution Chart
function renderCategoryChart(canvasId, verbatimCount, summaryCount, discardCount) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  const total = verbatimCount + summaryCount + discardCount;
  if (total === 0) {
    // Show empty state
    return;
  }

  return new Chart(canvas, {
    type: "doughnut",
    data: {
      labels: ["Keep Verbatim", "Summarize", "Discard"],
      datasets: [
        {
          data: [verbatimCount, summaryCount, discardCount],
          backgroundColor: ["#10b981", "#f59e0b", "#ef4444"],
          borderColor: "#1e293b",
          borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "bottom",
          labels: {
            color: "#94a3b8",
            font: { size: 12 },
          },
        },
      },
      cutout: "70%",
    },
  });
}

// Token Comparison Bar Chart
function renderTokenComparisonChart(canvasId, baselineTokens, palimpsestTokens) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  return new Chart(canvas, {
    type: "bar",
    data: {
      labels: ["Baseline (Full History / FIFO)", "PALIMPSEST (Selective Memory)"],
      datasets: [
        {
          label: "Token Consumption",
          data: [baselineTokens, palimpsestTokens],
          backgroundColor: ["#64748b", "#38bdf8"],
          borderRadius: 6,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          beginAtZero: true,
          grid: { color: "rgba(255, 255, 255, 0.05)" },
          ticks: { color: "#94a3b8" },
        },
        x: {
          grid: { display: false },
          ticks: { color: "#94a3b8" },
        },
      },
      plugins: {
        legend: { display: false },
      },
    },
  });
}
