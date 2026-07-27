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
// Single accent (blue) expressed as a tonal ramp, plus neutral grays for
// additional series — no purple/cyan/pink/neon.

const COLORS = [
  "#3b82f6", "#93c5fd", "#6b7280", "#1d4ed8",
  "#9ca3af", "#60a5fa", "#4b5563", "#2563eb",
];

const CHART_THEME = {
  background: "transparent",
  gridColor: "#1f2937",
  tickColor: "#6b7280",
  tooltipBg: "#111827",
  tooltipBorder: "#374151",
};

// ── Inline icons (SF Symbols-style: thin stroke, monochrome, no fill) ──────────

function IconBar(props) {
  return (
    <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M4 16.5V11M10 16.5V4M16 16.5v-8" />
    </svg>
  );
}

function IconLine(props) {
  return (
    <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M3 14.5 7.5 9l3.5 3 6-7" />
    </svg>
  );
}

function IconPie(props) {
  return (
    <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M10 3.5V10l5.5 3.2" />
      <circle cx="10" cy="10" r="6.5" />
    </svg>
  );
}

function IconHistogram(props) {
  return (
    <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M3 16.5V13M6.5 16.5V8M10 16.5v-9M13.5 16.5V6M17 16.5v-4" />
    </svg>
  );
}

function IconScatter(props) {
  return (
    <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor"
      strokeWidth="1.5" {...props}>
      <circle cx="5.5" cy="13.5" r="1.1" fill="currentColor" stroke="none" />
      <circle cx="9" cy="7.5" r="1.1" fill="currentColor" stroke="none" />
      <circle cx="13" cy="11" r="1.1" fill="currentColor" stroke="none" />
      <circle cx="15.5" cy="5.5" r="1.1" fill="currentColor" stroke="none" />
      <circle cx="7.5" cy="15.5" r="1.1" fill="currentColor" stroke="none" />
    </svg>
  );
}

// ── Custom Tooltip ─────────────────────────────────────────────────────────────

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 shadow-sm text-xs font-mono">
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
    bar: IconBar, line: IconLine, pie: IconPie,
    histogram: IconHistogram, scatter: IconScatter,
  };
  const ChartIcon = ICONS[viz.chart_type] || IconBar;

  return (
    <div className="mt-3">
      {/* Toggle button */}
      {!visible ? (
        <button
          onClick={() => setVisible(true)}
          className="flex items-center gap-2 text-xs font-medium text-gray-300 hover:text-gray-100 border border-gray-700 hover:border-gray-600 bg-gray-900 px-3 py-1.5 rounded-md transition-colors duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
          <ChartIcon className="text-blue-400" />
          Show {viz.chart_type} chart — {viz.title}
        </button>
      ) : (
        <div className="bg-gray-900/60 border border-gray-800 rounded-lg p-4">
          {/* Chart header */}
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="text-sm font-semibold text-gray-100">{viz.title}</div>
              <div className="text-xs text-gray-500 mt-0.5">{viz.reason}</div>
            </div>
            <button
              onClick={() => setVisible(false)}
              className="text-gray-500 hover:text-gray-300 text-xs font-mono border border-gray-800 hover:border-gray-700 px-2 py-1 rounded-md transition-colors duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
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
