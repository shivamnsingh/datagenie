// src/components/ChartRenderer.jsx
// ──────────────────────────────────
// Renders the correct chart type from a viz_suggestion + query rows.
// Uses Recharts (already available in the React artifact environment).
//
// Supported types: bar, line, pie, histogram, scatter
// Falls back to a clean table for anything else.

import { useState } from "react";
import {
  BarChart, Bar,
  LineChart, Line,
  PieChart, Pie, Cell,
  ScatterChart, Scatter,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from "recharts";

// ── Palette ───────────────────────────────────────────────────────────────────

const COLORS = [
  "#00e5ff", "#a855f7", "#22d3a0", "#f59e0b",
  "#f43f5e", "#3b82f6", "#84cc16", "#ec4899",
];

const CHART_THEME = {
  background: "transparent",
  gridColor: "#1f2937",
  tickColor: "#6b7280",
  tooltipBg: "#111827",
  tooltipBorder: "#374151",
};

// ── Custom Tooltip ─────────────────────────────────────────────────────────────

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-gray-900 border border-gray-700 rounded-xl px-3 py-2 shadow-xl text-xs font-mono">
      {label && <div className="text-gray-400 mb-1">{label}</div>}
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color || COLORS[0] }}>
          {p.name}: {typeof p.value === "number"
            ? p.value.toLocaleString(undefined, { maximumFractionDigits: 2 })
            : p.value}
        </div>
      ))}
    </div>
  );
}

// ── Custom Pie Label ──────────────────────────────────────────────────────────

function PieLabel({ cx, cy, midAngle, innerRadius, outerRadius, percent, name }) {
  if (percent < 0.04) return null;
  const RADIAN = Math.PI / 180;
  const radius = innerRadius + (outerRadius - innerRadius) * 0.5;
  const x = cx + radius * Math.cos(-midAngle * RADIAN);
  const y = cy + radius * Math.sin(-midAngle * RADIAN);
  return (
    <text x={x} y={y} fill="white" textAnchor="middle" dominantBaseline="central"
      fontSize={11} fontFamily="monospace">
      {`${(percent * 100).toFixed(0)}%`}
    </text>
  );
}

// ── Histogram helper — bucket raw values ──────────────────────────────────────

function bucketForHistogram(rows, col, buckets = 20) {
  const vals = rows
    .map(r => parseFloat(r[col]))
    .filter(v => !isNaN(v))
    .sort((a, b) => a - b);

  if (!vals.length) return [];

  const min = vals[0];
  const max = vals[vals.length - 1];
  const step = (max - min) / buckets || 1;

  const bins = Array.from({ length: buckets }, (_, i) => ({
    range: `${(min + i * step).toFixed(1)}`,
    count: 0,
  }));

  vals.forEach(v => {
    const idx = Math.min(Math.floor((v - min) / step), buckets - 1);
    bins[idx].count++;
  });

  return bins;
}

// ── Chart components ───────────────────────────────────────────────────────────

function BarChartView({ rows, viz }) {
  const data = rows.slice(0, 50);
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 48 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.gridColor} />
        <XAxis
          dataKey={viz.x_col}
          tick={{ fill: CHART_THEME.tickColor, fontSize: 11, fontFamily: "monospace" }}
          angle={-35} textAnchor="end"
        />
        <YAxis tick={{ fill: CHART_THEME.tickColor, fontSize: 11 }} />
        <Tooltip content={<CustomTooltip />} />
        <Bar dataKey={viz.y_col} radius={[4, 4, 0, 0]}>
          {data.map((_, i) => (
            <Cell key={i} fill={COLORS[i % COLORS.length]} fillOpacity={0.85} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function LineChartView({ rows, viz }) {
  const data = rows.slice(0, 200);
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 48 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.gridColor} />
        <XAxis
          dataKey={viz.x_col}
          tick={{ fill: CHART_THEME.tickColor, fontSize: 11, fontFamily: "monospace" }}
          angle={-35} textAnchor="end"
        />
        <YAxis tick={{ fill: CHART_THEME.tickColor, fontSize: 11 }} />
        <Tooltip content={<CustomTooltip />} />
        <Line
          type="monotone"
          dataKey={viz.y_col}
          stroke={COLORS[0]}
          strokeWidth={2}
          dot={data.length < 30 ? { fill: COLORS[0], r: 3 } : false}
          activeDot={{ r: 5 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

function PieChartView({ rows, viz }) {
  const data = rows.slice(0, 12).map(r => ({
    name: String(r[viz.x_col] ?? "—"),
    value: parseFloat(r[viz.y_col]) || 0,
  }));
  return (
    <ResponsiveContainer width="100%" height={260}>
      <PieChart>
        <Pie
          data={data}
          dataKey="value"
          nameKey="name"
          cx="50%" cy="50%"
          outerRadius={100}
          labelLine={false}
          label={PieLabel}
        >
          {data.map((_, i) => (
            <Cell key={i} fill={COLORS[i % COLORS.length]} />
          ))}
        </Pie>
        <Tooltip content={<CustomTooltip />} />
        <Legend
          formatter={(v) => (
            <span style={{ color: "#9ca3af", fontSize: 11, fontFamily: "monospace" }}>{v}</span>
          )}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}

function HistogramView({ rows, viz }) {
  const data = bucketForHistogram(rows, viz.x_col);
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 16 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.gridColor} />
        <XAxis dataKey="range" tick={{ fill: CHART_THEME.tickColor, fontSize: 10 }} />
        <YAxis tick={{ fill: CHART_THEME.tickColor, fontSize: 11 }} />
        <Tooltip content={<CustomTooltip />} />
        <Bar dataKey="count" fill={COLORS[0]} fillOpacity={0.75} radius={[2, 2, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function ScatterView({ rows, viz }) {
  const data = rows.slice(0, 300).map(r => ({
    x: parseFloat(r[viz.x_col]) || 0,
    y: parseFloat(r[viz.y_col]) || 0,
  }));
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ScatterChart margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.gridColor} />
        <XAxis
          dataKey="x" name={viz.x_col}
          tick={{ fill: CHART_THEME.tickColor, fontSize: 11 }}
          label={{ value: viz.x_col, position: "insideBottom", offset: -4, fill: "#6b7280", fontSize: 11 }}
        />
        <YAxis
          dataKey="y" name={viz.y_col}
          tick={{ fill: CHART_THEME.tickColor, fontSize: 11 }}
        />
        <Tooltip content={<CustomTooltip />} cursor={{ strokeDasharray: "3 3" }} />
        <Scatter data={data} fill={COLORS[0]} fillOpacity={0.6} />
      </ScatterChart>
    </ResponsiveContainer>
  );
}

// ── Main export ────────────────────────────────────────────────────────────────

/**
 * ChartRenderer
 *
 * Props:
 *   viz    — VizSuggestion from the SQL engine
 *   rows   — array of row objects from the query result
 *   title  — optional override title
 */
export default function ChartRenderer({ viz, rows }) {
  const [visible, setVisible] = useState(false);

  if (!viz || !rows?.length || viz.chart_type === "table") return null;

  const ICONS = {
    bar: "📊", line: "📈", pie: "🥧",
    histogram: "📉", scatter: "🔵",
  };

  return (
    <div className="mt-3">
      {/* Toggle button */}
      {!visible ? (
        <button
          onClick={() => setVisible(true)}
          className="flex items-center gap-2 text-xs font-semibold text-purple-400 hover:text-purple-300 border border-purple-800/50 hover:border-purple-600 bg-purple-950/20 hover:bg-purple-950/40 px-3 py-2 rounded-xl transition-all">
          <span>{ICONS[viz.chart_type] || "📊"}</span>
          Show {viz.chart_type} chart — {viz.title}
        </button>
      ) : (
        <div className="bg-gray-900/60 border border-gray-800 rounded-2xl p-4">
          {/* Chart header */}
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="text-sm font-bold text-white">{viz.title}</div>
              <div className="text-xs text-gray-500 mt-0.5">{viz.reason}</div>
            </div>
            <button
              onClick={() => setVisible(false)}
              className="text-gray-600 hover:text-gray-400 text-xs font-mono border border-gray-800 px-2 py-1 rounded-lg transition-colors">
              hide
            </button>
          </div>

          {/* Chart */}
          {viz.chart_type === "bar"       && <BarChartView rows={rows} viz={viz} />}
          {viz.chart_type === "line"      && <LineChartView rows={rows} viz={viz} />}
          {viz.chart_type === "pie"       && <PieChartView rows={rows} viz={viz} />}
          {viz.chart_type === "histogram" && <HistogramView rows={rows} viz={viz} />}
          {viz.chart_type === "scatter"   && <ScatterView rows={rows} viz={viz} />}

          {/* Axis labels */}
          {(viz.x_col || viz.y_col) && (
            <div className="flex justify-between mt-2 px-1">
              {viz.x_col && (
                <span className="text-xs font-mono text-gray-600">x: {viz.x_col}</span>
              )}
              {viz.y_col && (
                <span className="text-xs font-mono text-gray-600">y: {viz.y_col}</span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
