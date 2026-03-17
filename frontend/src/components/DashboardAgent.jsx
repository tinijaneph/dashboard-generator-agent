import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Send, Plus, Trash2, BarChart3, TrendingUp, Users, Download,
  ChevronLeft, ChevronRight, Maximize2, Minimize2, FileText,
  Presentation, Palette, Filter, PlusCircle, Lightbulb,
  RefreshCw, X, Check, ChevronDown, Sparkles, LayoutDashboard,
  ArrowUpRight, ArrowDownRight, Minus
} from 'lucide-react';
import {
  BarChart, Bar, LineChart, Line,
  PieChart as RechartsPieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, ComposedChart, Area, AreaChart,
  LabelList, ReferenceLine
} from 'recharts';

// ─── THEMES ──────────────────────────────────────────────────────────────────
const THEMES = {
  brickblue: {
    name: 'Brick Blue',
    bg: '#eef2f7',
    surface: '#ffffff',
    surfaceAlt: '#f4f7fb',
    border: '#dce4ef',
    headerBg: '#0a2342',
    text: '#0d1f3c',
    textMuted: '#5a7184',
    textLight: '#8fa3b8',
    accent: '#1a6bb5',
    accentLight: '#e8f1fb',
    accentText: '#1a6bb5',
    positive: '#0d7a4e',
    positiveBg: '#e6f5ee',
    negative: '#b91c1c',
    negativeBg: '#fee2e2',
    neutral: '#5a7184',
    neutralBg: '#f0f4f8',
    colors: ['#1a6bb5','#0a2342','#2196f3','#64b5f6','#0d7a4e','#f59e0b','#7c3aed','#dc2626'],
    chartGrid: '#e8eef5',
    tableHeaderBg: '#c9a96e',
    tableHeaderText: '#ffffff',
    tableRowAlt: '#faf8f5',
    kpiAccent: '#1a6bb5',
    sectionTitle: '#1a6bb5',
  },
  dark: {
    name: 'Dark',
    bg: '#0f1117',
    surface: '#1a1f2e',
    surfaceAlt: '#141820',
    border: '#2d3748',
    headerBg: '#111827',
    text: '#f1f5f9',
    textMuted: '#94a3b8',
    textLight: '#64748b',
    accent: '#6366f1',
    accentLight: '#1e1b4b',
    accentText: '#818cf8',
    positive: '#34d399',
    positiveBg: '#064e3b',
    negative: '#f87171',
    negativeBg: '#450a0a',
    neutral: '#94a3b8',
    neutralBg: '#1e293b',
    colors: ['#6366f1','#22d3ee','#a78bfa','#34d399','#fbbf24','#f87171','#f472b6','#2dd4bf'],
    chartGrid: '#2d3748',
    tableHeaderBg: '#374151',
    tableHeaderText: '#f9fafb',
    tableRowAlt: '#1e2533',
    kpiAccent: '#6366f1',
    sectionTitle: '#818cf8',
  },
  clean: {
    name: 'Clean',
    bg: '#fafafa',
    surface: '#ffffff',
    surfaceAlt: '#f5f5f5',
    border: '#e0e0e0',
    headerBg: '#212121',
    text: '#212121',
    textMuted: '#616161',
    textLight: '#9e9e9e',
    accent: '#1565c0',
    accentLight: '#e3f2fd',
    accentText: '#1565c0',
    positive: '#2e7d32',
    positiveBg: '#e8f5e9',
    negative: '#c62828',
    negativeBg: '#ffebee',
    neutral: '#616161',
    neutralBg: '#f5f5f5',
    colors: ['#1565c0','#0288d1','#00897b','#43a047','#f9a825','#e53935','#8e24aa','#00acc1'],
    chartGrid: '#eeeeee',
    tableHeaderBg: '#1565c0',
    tableHeaderText: '#ffffff',
    tableRowAlt: '#f5f5f5',
    kpiAccent: '#1565c0',
    sectionTitle: '#1565c0',
  },
  emerald: {
    name: 'Emerald',
    bg: '#f0fdf4',
    surface: '#ffffff',
    surfaceAlt: '#f0fdf4',
    border: '#bbf7d0',
    headerBg: '#064e3b',
    text: '#064e3b',
    textMuted: '#047857',
    textLight: '#6ee7b7',
    accent: '#059669',
    accentLight: '#d1fae5',
    accentText: '#059669',
    positive: '#059669',
    positiveBg: '#d1fae5',
    negative: '#dc2626',
    negativeBg: '#fee2e2',
    neutral: '#047857',
    neutralBg: '#ecfdf5',
    colors: ['#059669','#0891b2','#7c3aed','#d97706','#dc2626','#0284c7','#65a30d','#db2777'],
    chartGrid: '#d1fae5',
    tableHeaderBg: '#059669',
    tableHeaderText: '#ffffff',
    tableRowAlt: '#f0fdf4',
    kpiAccent: '#059669',
    sectionTitle: '#059669',
  },
  slate: {
    name: 'Slate',
    bg: '#f8fafc',
    surface: '#ffffff',
    surfaceAlt: '#f1f5f9',
    border: '#e2e8f0',
    headerBg: '#1e293b',
    text: '#1e293b',
    textMuted: '#475569',
    textLight: '#94a3b8',
    accent: '#7c3aed',
    accentLight: '#ede9fe',
    accentText: '#7c3aed',
    positive: '#059669',
    positiveBg: '#d1fae5',
    negative: '#dc2626',
    negativeBg: '#fee2e2',
    neutral: '#475569',
    neutralBg: '#f1f5f9',
    colors: ['#7c3aed','#2563eb','#0891b2','#059669','#d97706','#dc2626','#db2777','#0284c7'],
    chartGrid: '#e2e8f0',
    tableHeaderBg: '#7c3aed',
    tableHeaderText: '#ffffff',
    tableRowAlt: '#faf5ff',
    kpiAccent: '#7c3aed',
    sectionTitle: '#7c3aed',
  },
};

const API_URL = import.meta.env.VITE_API_URL || 'https://dashboard-agent-mbhsrssbzq-uc.a.run.app';

// ─── CHART RENDERER ───────────────────────────────────────────────────────────
// Helper: smart number formatter (100000 → 100K, 1500000 → 1.5M)
const fmtNum = (v) => {
  if (v === null || v === undefined) return '';
  const n = Number(v);
  if (isNaN(n)) return String(v);
  if (Math.abs(n) >= 1000000) return `${(n/1000000).toFixed(1)}M`;
  if (Math.abs(n) >= 1000) return `${(n/1000).toFixed(n >= 10000 ? 0 : 1)}K`;
  if (Number.isInteger(n)) return n.toLocaleString();
  return n.toFixed(1);
};

const CustomLabel = ({ x, y, width, value, fill }) => {
  if (!value && value !== 0) return null;
  const label = fmtNum(value);
  return (
    <text x={x + width / 2} y={y - 4} fill={fill || '#64748b'} textAnchor="middle" fontSize={10} fontWeight={600}>
      {label}
    </text>
  );
};

const renderChart = (viz, theme) => {
  const data = viz.computed_data || generateFallbackData(viz);
  const C = theme.colors;
  const isDark = theme.bg === '#0f1117';

  const tooltipStyle = {
    background: theme.surface, border: `1px solid ${theme.border}`,
    borderRadius: 8, color: theme.text, fontSize: 12,
    boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
    padding: '8px 12px',
  };
  const axisStyle = { fontSize: 11, fill: theme.textMuted, fontFamily: 'inherit' };
  const gridProps = { strokeDasharray: '3 3', stroke: theme.chartGrid, vertical: false };
  const legendStyle = { wrapperStyle: { fontSize: 11, color: theme.textMuted, paddingTop: 6 } };

  // ── TABLE ──────────────────────────────────────────────────────────────────
  if (viz.type === 'table') {
    if (!data || data.length === 0) return (
      <div style={{ padding: 20, textAlign: 'center', color: theme.textMuted, fontSize: 13 }}>No data available</div>
    );
    const cols = Object.keys(data[0]);
    return (
      <div style={{ overflowX: 'auto', marginTop: 4 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr>{cols.map((c, i) => (
              <th key={i} style={{ padding: '10px 16px', textAlign: i === 0 ? 'left' : 'right', background: theme.tableHeaderBg, color: theme.tableHeaderText, fontWeight: 600, fontSize: 11, letterSpacing: '0.4px', textTransform: 'uppercase' }}>{c}</th>
            ))}</tr>
          </thead>
          <tbody>
            {data.map((row, ri) => (
              <tr key={ri} style={{ background: ri % 2 === 1 ? theme.tableRowAlt : theme.surface, transition: 'background 0.1s' }}>
                {cols.map((c, ci) => (
                  <td key={ci} style={{ padding: '10px 16px', color: ci === 0 ? theme.text : theme.textMuted, fontWeight: ci === 0 ? 600 : 400, textAlign: ci === 0 ? 'left' : 'right', borderBottom: `1px solid ${theme.border}`, fontSize: 13 }}>{String(row[c] ?? '')}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  // ── SIMPLE BAR (with value labels on top) ─────────────────────────────────
  if (viz.type === 'bar') {
    const keys = data.length > 0 ? Object.keys(data[0]).filter(k => k !== 'name') : ['value'];
    const isMulti = keys.length > 1;
    const height = Math.max(240, data.length * 28);
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ top: 20, right: 10, left: -10, bottom: 4 }}>
          <CartesianGrid {...gridProps} />
          <XAxis dataKey="name" tick={axisStyle} axisLine={false} tickLine={false} />
          <YAxis tick={axisStyle} axisLine={false} tickLine={false} tickFormatter={fmtNum} />
          <Tooltip contentStyle={tooltipStyle} cursor={{ fill: `${C[0]}18` }} formatter={(v, name) => [fmtNum(v), name]} />
          {isMulti && <Legend {...legendStyle} />}
          {keys.map((k, i) => (
            <Bar key={k} dataKey={k} fill={C[i % C.length]}
              radius={isMulti ? [3,3,0,0] : [5,5,0,0]}
              maxBarSize={52}>
              {!isMulti && (
                <LabelList dataKey={k} position="top" style={{ fontSize: 10, fontWeight: 600, fill: theme.textMuted }} formatter={fmtNum} />
              )}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    );
  }

  // ── STACKED BAR (with total labels on top) ────────────────────────────────
  if (viz.type === 'stacked_bar') {
    const keys = data.length > 0 ? Object.keys(data[0]).filter(k => k !== 'name') : ['value'];
    return (
      <ResponsiveContainer width="100%" height={250}>
        <BarChart data={data} margin={{ top: 20, right: 10, left: -10, bottom: 4 }}>
          <CartesianGrid {...gridProps} />
          <XAxis dataKey="name" tick={axisStyle} axisLine={false} tickLine={false} />
          <YAxis tick={axisStyle} axisLine={false} tickLine={false} tickFormatter={fmtNum} />
          <Tooltip contentStyle={tooltipStyle} cursor={{ fill: `${C[0]}18` }} formatter={(v, name) => [fmtNum(v), name]} />
          <Legend {...legendStyle} />
          {keys.map((k, i) => {
            const isLast = i === keys.length - 1;
            return (
              <Bar key={k} dataKey={k} fill={C[i % C.length]} stackId="stack" maxBarSize={56}
                radius={isLast ? [4,4,0,0] : [0,0,0,0]}>
                {isLast && (
                  <LabelList dataKey={k} position="top" style={{ fontSize: 10, fontWeight: 600, fill: theme.textMuted }} formatter={fmtNum} />
                )}
              </Bar>
            );
          })}
        </BarChart>
      </ResponsiveContainer>
    );
  }

  // ── GROUPED BAR (value labels inside/above each bar) ─────────────────────
  if (viz.type === 'grouped_bar') {
    const keys = data.length > 0 ? Object.keys(data[0]).filter(k => k !== 'name') : ['value'];
    return (
      <ResponsiveContainer width="100%" height={250}>
        <BarChart data={data} margin={{ top: 20, right: 10, left: -10, bottom: 4 }} barGap={2} barCategoryGap="25%">
          <CartesianGrid {...gridProps} />
          <XAxis dataKey="name" tick={axisStyle} axisLine={false} tickLine={false} />
          <YAxis tick={axisStyle} axisLine={false} tickLine={false} tickFormatter={fmtNum} />
          <Tooltip contentStyle={tooltipStyle} cursor={{ fill: `${C[0]}18` }} formatter={(v, name) => [fmtNum(v), name]} />
          <Legend {...legendStyle} />
          {keys.map((k, i) => (
            <Bar key={k} dataKey={k} fill={C[i % C.length]} radius={[4,4,0,0]} maxBarSize={36}>
              <LabelList dataKey={k} position="top" style={{ fontSize: 10, fontWeight: 600, fill: theme.textMuted }} formatter={fmtNum} />
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    );
  }

  // ── HORIZONTAL BAR ────────────────────────────────────────────────────────
  if (viz.type === 'horizontal_bar') {
    const keys = data.length > 0 ? Object.keys(data[0]).filter(k => k !== 'name') : ['value'];
    const isMulti = keys.length > 1;
    const h = Math.max(220, data.length * (isMulti ? 52 : 38));
    return (
      <ResponsiveContainer width="100%" height={h}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 50, left: 4, bottom: 4 }} barCategoryGap="20%">
          <CartesianGrid strokeDasharray="3 3" stroke={theme.chartGrid} horizontal={false} />
          <XAxis type="number" tick={axisStyle} axisLine={false} tickLine={false} tickFormatter={fmtNum} />
          <YAxis type="category" dataKey="name" tick={{ ...axisStyle, fontSize: 11 }} width={115} axisLine={false} tickLine={false} />
          <Tooltip contentStyle={tooltipStyle} cursor={{ fill: `${C[0]}18` }} formatter={(v, name) => [fmtNum(v), name]} />
          {isMulti && <Legend {...legendStyle} />}
          {keys.map((k, i) => (
            <Bar key={k} dataKey={k} fill={C[i % C.length]} radius={[0,4,4,0]} maxBarSize={28}>
              <LabelList dataKey={k} position="right" style={{ fontSize: 10, fontWeight: 600, fill: theme.textMuted }} formatter={fmtNum} />
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    );
  }

  // ── MULTI-LINE (Brick AI style — smooth curves, filled dots) ─────────────
  if (viz.type === 'line') {
    const keys = data.length > 0 ? Object.keys(data[0]).filter(k => k !== 'name') : ['value'];
    const isMulti = keys.length > 1;
    return (
      <ResponsiveContainer width="100%" height={240}>
        <ComposedChart data={data} margin={{ top: 16, right: 16, left: -10, bottom: 4 }}>
          <defs>
            {keys.map((k, i) => (
              <linearGradient key={k} id={`lineGrad-${i}-${viz.id}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={C[i % C.length]} stopOpacity={0.15} />
                <stop offset="95%" stopColor={C[i % C.length]} stopOpacity={0} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid {...gridProps} />
          <XAxis dataKey="name" tick={axisStyle} axisLine={false} tickLine={false} />
          <YAxis tick={axisStyle} axisLine={false} tickLine={false} tickFormatter={fmtNum} />
          <Tooltip contentStyle={tooltipStyle} formatter={(v, name) => [fmtNum(v), name]} />
          {isMulti && <Legend {...legendStyle} />}
          {keys.map((k, i) => (
            <React.Fragment key={k}>
              <Area type="monotone" dataKey={k} stroke="none" fill={`url(#lineGrad-${i}-${viz.id})`} />
              <Line type="monotone" dataKey={k} stroke={C[i % C.length]} strokeWidth={2.5}
                dot={{ r: 3, fill: theme.surface, stroke: C[i % C.length], strokeWidth: 2 }}
                activeDot={{ r: 5, fill: C[i % C.length] }} />
            </React.Fragment>
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    );
  }

  // ── COMPOSED — bar + line dual axis (Brick AI's signature chart) ──────────
  if (viz.type === 'composed') {
    const keys = data.length > 0 ? Object.keys(data[0]).filter(k => k !== 'name') : [];
    const barKey = keys[0];
    const lineKey = keys[1];
    return (
      <ResponsiveContainer width="100%" height={250}>
        <ComposedChart data={data} margin={{ top: 20, right: 36, left: -10, bottom: 4 }}>
          <CartesianGrid {...gridProps} />
          <XAxis dataKey="name" tick={axisStyle} axisLine={false} tickLine={false} />
          <YAxis yAxisId="left" tick={axisStyle} axisLine={false} tickLine={false} tickFormatter={fmtNum} />
          {lineKey && (
            <YAxis yAxisId="right" orientation="right" tick={axisStyle} axisLine={false} tickLine={false} tickFormatter={fmtNum} />
          )}
          <Tooltip contentStyle={tooltipStyle} formatter={(v, name) => [fmtNum(v), name]} />
          <Legend {...legendStyle} />
          {barKey && (
            <Bar yAxisId="left" dataKey={barKey} fill={C[0]} radius={[5,5,0,0]} maxBarSize={44}>
              <LabelList dataKey={barKey} position="top" style={{ fontSize: 10, fontWeight: 600, fill: theme.textMuted }} formatter={fmtNum} />
            </Bar>
          )}
          {lineKey && (
            <Line yAxisId="right" type="monotone" dataKey={lineKey} stroke={C[1]} strokeWidth={2.5}
              dot={{ r: 5, fill: theme.surface, stroke: C[1], strokeWidth: 2 }}
              activeDot={{ r: 6, fill: C[1] }} />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    );
  }

  // ── DONUT / PIE ───────────────────────────────────────────────────────────
  if (viz.type === 'pie' || viz.type === 'donut') {
    return (
      <ResponsiveContainer width="100%" height={240}>
        <RechartsPieChart>
          <Pie data={data} cx="50%" cy="50%"
            outerRadius={88} innerRadius={viz.type === 'donut' ? 52 : 0}
            dataKey="value" paddingAngle={viz.type === 'donut' ? 2 : 0}
            labelLine={false}
            label={({ cx, cy, midAngle, innerRadius, outerRadius, value, percent }) => {
              if (percent < 0.06) return null;
              const RADIAN = Math.PI / 180;
              const radius = innerRadius + (outerRadius - innerRadius) * 0.5;
              const x = cx + radius * Math.cos(-midAngle * RADIAN);
              const y = cy + radius * Math.sin(-midAngle * RADIAN);
              return (
                <text x={x} y={y} fill="#ffffff" textAnchor="middle" dominantBaseline="central"
                  fontSize={11} fontWeight={700}>
                  {fmtNum(value)}
                </text>
              );
            }}>
            {data.map((_, i) => <Cell key={i} fill={C[i % C.length]} />)}
          </Pie>
          <Tooltip contentStyle={tooltipStyle} formatter={(v, name) => [fmtNum(v), name]} />
          <Legend {...legendStyle} />
        </RechartsPieChart>
      </ResponsiveContainer>
    );
  }

  return (
    <div style={{ height: 180, display: 'flex', alignItems: 'center', justifyContent: 'center', color: theme.textMuted, fontSize: 13 }}>
      Chart type "{viz.type}" not yet supported
    </div>
  );
};

function generateFallbackData(viz) {
  if (viz.type === 'pie' || viz.type === 'donut') return [
    { name: 'Active', value: 820 }, { name: 'Inactive', value: 310 }, { name: 'On Leave', value: 120 }
  ];
  if (viz.type === 'line') return [
    { name: 'Jan', Headcount: 980, Attrition: 82 }, { name: 'Feb', Headcount: 995, Attrition: 76 },
    { name: 'Mar', Headcount: 1010, Attrition: 91 }, { name: 'Apr', Headcount: 1008, Attrition: 68 },
    { name: 'May', Headcount: 1020, Attrition: 74 }, { name: 'Jun', Headcount: 1035, Attrition: 88 },
  ];
  if (viz.type === 'composed') return [
    { name: 'Band I', Count: 420, Rate: 31 }, { name: 'Band II', Count: 310, Rate: 18 },
    { name: 'Band III', Count: 220, Rate: 12 }, { name: 'Band IV', Count: 140, Rate: 7 }, { name: 'Band V', Count: 80, Rate: 4 },
  ];
  if (viz.type === 'stacked_bar') return [
    { name: 'Finance', Permanent: 280, Temporary: 95, Internship: 45 },
    { name: 'Sales', Permanent: 210, Temporary: 120, Internship: 80 },
    { name: 'HR', Permanent: 190, Temporary: 60, Internship: 30 },
    { name: 'IT', Permanent: 340, Temporary: 85, Internship: 55 },
    { name: 'Operations', Permanent: 260, Temporary: 140, Internship: 90 },
  ];
  if (viz.type === 'grouped_bar') return [
    { name: 'Finance', Active: 280, Inactive: 108 }, { name: 'Marketing', Active: 320, Inactive: 130 },
    { name: 'Sales', Active: 354, Inactive: 92 }, { name: 'HR', Active: 310, Inactive: 118 },
    { name: 'IT', Active: 295, Inactive: 115 }, { name: 'Operations', Active: 340, Inactive: 130 },
  ];
  if (viz.type === 'table') return [];
  if (viz.type === 'horizontal_bar') return [
    { name: 'Operations', Inactive: 420 }, { name: 'Sales', Inactive: 354 },
    { name: 'Marketing', Inactive: 298 }, { name: 'IT', Inactive: 241 },
    { name: 'Finance', Inactive: 189 }, { name: 'HR', Inactive: 112 },
  ];
  return [
    { name: 'EMEA', value: 3840 }, { name: 'APAC', value: 2950 },
    { name: 'Americas', value: 2180 }, { name: 'MEA', value: 880 },
  ];
}

// ─── TREND BADGE ─────────────────────────────────────────────────────────────
const TrendBadge = ({ trend, change, theme }) => {
  if (!trend && !change) return null;
  const up = trend === 'up'; const neutral = trend === 'stable' || !trend;
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 99, background: neutral ? theme.neutralBg : up ? theme.positiveBg : theme.negativeBg, color: neutral ? theme.neutral : up ? theme.positive : theme.negative }}>
      {neutral ? <Minus className="w-3 h-3" /> : up ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
      {change || trend}
    </span>
  );
};

// ─── PDF EXPORT ──────────────────────────────────────────────────────────────
function exportToPDF(dashboard, theme) {
  const win = window.open('', '_blank');
  const metricsHTML = (dashboard.metrics || []).map(m => `<div class="kpi"><div class="kpi-label">${m.label}</div><div class="kpi-value">${m.value}</div>${m.change ? `<span class="kpi-badge">${m.change}</span>` : ''}</div>`).join('');
  const vizHTML = (dashboard.visualizations || []).map(v => `<div class="viz-row"><div class="viz-chart"><div class="viz-title">${v.title}</div><div class="viz-desc">${v.description || ''}</div><div class="placeholder">[${v.type} chart]</div></div><div class="viz-insights"><div class="ins-label">Key Insights</div>${(v.key_insights || []).map(i => `<div class="ins-item">• ${i}</div>`).join('')}</div></div>`).join('');
  win.document.write(`<!DOCTYPE html><html><head><title>${dashboard.title}</title><style>
    body{font-family:'Segoe UI',sans-serif;background:#eef2f7;color:#0d1f3c;padding:32px;margin:0}
    .header{background:#0a2342;color:#fff;padding:22px 28px;border-radius:12px;margin-bottom:20px}
    h1{margin:0;font-size:20px;font-weight:700}
    .overview{color:#5a7184;font-size:14px;line-height:1.7;margin-bottom:20px}
    .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-bottom:20px}
    .kpi{background:#fff;border:1px solid #dce4ef;border-radius:10px;padding:16px}
    .kpi-label{font-size:10px;color:#5a7184;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px}
    .kpi-value{font-size:24px;font-weight:700;color:#1a6bb5}
    .kpi-badge{font-size:11px;background:#e8f1fb;color:#1a6bb5;padding:2px 7px;border-radius:99px;display:inline-block;margin-top:5px}
    .ins-box{background:#fff;border:1px solid #dce4ef;border-radius:10px;padding:14px 18px;margin-bottom:18px}
    .ins-box ul{margin:6px 0 0;padding-left:16px}
    .ins-box li{font-size:13px;color:#5a7184;margin-bottom:5px;line-height:1.5}
    .viz-row{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px;page-break-inside:avoid}
    .viz-chart{background:#fff;border:1px solid #dce4ef;border-radius:10px;padding:16px}
    .viz-title{font-size:14px;font-weight:600;color:#0d1f3c;margin-bottom:4px}
    .viz-desc{font-size:12px;color:#5a7184;margin-bottom:10px;line-height:1.5}
    .placeholder{height:70px;background:#f0f4f8;border-radius:6px;display:flex;align-items:center;justify-content:center;color:#8fa3b8;font-size:12px}
    .viz-insights{background:#f4f7fb;border:1px solid #dce4ef;border-radius:10px;padding:14px}
    .ins-label{font-size:12px;font-weight:700;color:#1a6bb5;margin-bottom:8px}
    .ins-item{font-size:12px;color:#5a7184;margin-bottom:6px;line-height:1.5}
    @media print{body{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
  </style></head><body>
  <div class="header"><h1>${dashboard.title}</h1></div>
  <div class="overview">${dashboard.overview || ''}</div>
  <div class="kpis">${metricsHTML}</div>
  ${(dashboard.overall_insights || []).length ? `<div class="ins-box"><strong style="font-size:13px">Overall Insights</strong><ul>${(dashboard.overall_insights || []).map(i => `<li>${i}</li>`).join('')}</ul></div>` : ''}
  ${vizHTML}
  </body></html>`);
  win.document.close();
  setTimeout(() => win.print(), 900);
}

// ─── ACTION CHIPS ─────────────────────────────────────────────────────────────
const ACTIONS = [
  { icon: <Palette className="w-3.5 h-3.5" />, label: 'Explore themes', type: 'themes' },
  { icon: <PlusCircle className="w-3.5 h-3.5" />, label: 'Add charts', type: 'add_charts' },
  { icon: <Filter className="w-3.5 h-3.5" />, label: 'Add filters', type: 'add_filters' },
  { icon: <Lightbulb className="w-3.5 h-3.5" />, label: 'Key insights', type: 'insights' },
  { icon: <RefreshCw className="w-3.5 h-3.5" />, label: 'Refresh data', type: 'refresh' },
];

// ─── MAIN COMPONENT ───────────────────────────────────────────────────────────
const DashboardAgent = () => {
  const [chats, setChats] = useState([]);
  const [activeChat, setActiveChat] = useState(null);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [showLanding, setShowLanding] = useState(true);
  const [showSidebar, setShowSidebar] = useState(true);
  const [showChat, setShowChat] = useState(true);
  const [presentMode, setPresentMode] = useState(false);
  const [activeTheme, setActiveTheme] = useState('brickblue');
  const [showThemeModal, setShowThemeModal] = useState(false);
  const [showExportMenu, setShowExportMenu] = useState(false);
  const [actionPanel, setActionPanel] = useState(null);
  const [genStep, setGenStep] = useState('');
  const [suggestions, setSuggestions] = useState([]);
  const [activeFilters, setActiveFilters] = useState([]); // [{field, options, selected}]
  const [openFilterDropdown, setOpenFilterDropdown] = useState(null);
  const msgEndRef = useRef(null);

  const theme = THEMES[activeTheme];
  const activeChartData = chats.find(c => c.id === activeChat);
  const dashboard = activeChartData?.dashboard;

  useEffect(() => { msgEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [chats, loading]);

  const LANDING_PROMPTS = [
    { icon: <TrendingUp className="w-4 h-4" />, label: 'Attrition & Retention', prompt: 'Analyze attrition trends and identify which groups have highest turnover risk' },
    { icon: <Users className="w-4 h-4" />, label: 'Workforce Overview', prompt: 'Create a comprehensive workforce overview showing headcount by function, band, and region' },
    { icon: <BarChart3 className="w-4 h-4" />, label: 'Demographics', prompt: 'Show a full demographics dashboard: gender, age group, collar type, and contract type' },
    { icon: <LayoutDashboard className="w-4 h-4" />, label: 'Org Structure', prompt: 'Visualize organizational structure breakdown by supervisory levels, job families, and bands' },
  ];

  const createNewChat = useCallback((prompt = null) => {
    const id = Date.now();
    setChats(p => [...p, { id, title: 'New Dashboard', messages: [], dashboard: null }]);
    setActiveChat(id);
    setShowLanding(false);
    setSuggestions([]);
    setActionPanel(null);
    if (prompt) setTimeout(() => sendMessage(prompt, id, []), 80);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const deleteChat = (chatId) => {
    setChats(p => p.filter(c => c.id !== chatId));
    if (activeChat === chatId) { setActiveChat(null); setShowLanding(true); }
  };

  // ── Filter helpers ──────────────────────────────────────────────────────
  const addFilter = (field) => {
    if (activeFilters.find(f => f.field === field)) return;
    // Extract unique values from dashboard visualizations or use defaults
    const defaults = {
      'Function': ['Finance','Marketing','Sales','HR','IT','Operations'],
      'Reporting_Region': ['EMEA','APAC','Americas','MEA'],
      'Band': ['Band I','Band II','Band III','Band IV','Band V'],
      'Contract_Type': ['Permanent','Temporary','Internship','Freelance'],
      'Snapshot_Year': ['2022','2023','2024','2025'],
      'Gender': ['Male','Female'],
      'Blue_White_Collar': ['Blue Collar','White Collar'],
      'Worker_Category': ['Employee','Contractor','Intern'],
    };
    const options = defaults[field] || [field];
    setActiveFilters(p => [...p, { field, options, selected: [...options] }]);
    setOpenFilterDropdown(field);
    setActionPanel(null);
  };

  const removeFilter = (field) => {
    setActiveFilters(p => p.filter(f => f.field !== field));
    setOpenFilterDropdown(null);
  };

  const toggleFilterOption = (field, option) => {
    setActiveFilters(p => p.map(f => f.field === field
      ? { ...f, selected: f.selected.includes(option) ? f.selected.filter(o => o !== option) : [...f.selected, option] }
      : f));
  };

  const toggleAllFilter = (field) => {
    setActiveFilters(p => p.map(f => f.field === field
      ? { ...f, selected: f.selected.length === f.options.length ? [] : [...f.options] }
      : f));
  };

  const sendMessage = useCallback(async (message, chatId, history) => {
    if (!message?.trim()) return;
    const cid = chatId || activeChat;
    if (!cid) return;
    const currentChat = chats.find(c => c.id === cid);
    setChats(p => p.map(c => c.id === cid ? { ...c, messages: [...c.messages, { role: 'user', content: message }] } : c));
    setInput('');
    setLoading(true);
    setGenStep('Analyzing your request…');
    setActionPanel(null);
    try {
      setGenStep('Generating dashboard…');
      const res = await fetch(`${API_URL}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, history: (history || currentChat?.messages || []).slice(-6), current_dashboard: currentChat?.dashboard || null }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setGenStep('Rendering visualizations…');
      const data = await res.json();
      setSuggestions(data.suggestions || []);
      setChats(p => p.map(c => c.id === cid ? { ...c, messages: [...c.messages, { role: 'assistant', content: data.response || 'Dashboard generated.' }], dashboard: data.dashboard || c.dashboard, title: data.dashboard?.title || c.title } : c));
    } catch (err) {
      console.error(err);
      setChats(p => p.map(c => c.id === cid ? { ...c, messages: [...c.messages, { role: 'assistant', content: 'Sorry, something went wrong. Please try again.' }] } : c));
    } finally { setLoading(false); setGenStep(''); }
  }, [activeChat, chats]);

  const handleSend = () => {
    if (!input.trim() || loading) return;
    if (!activeChat) { createNewChat(input); return; }
    sendMessage(input, activeChat, activeChartData?.messages || []);
  };

  const handleSuggestionSend = (text) => {
    setInput('');
    sendMessage(text, activeChat, activeChartData?.messages || []);
  };

  const getChartSuggestions = () => {
    const existing = (dashboard?.visualizations || []).map(v => v.title.toLowerCase());
    return [
      'Headcount by Function over time', 'Gender distribution by Band',
      'Active vs Inactive by Region', 'FTE by Worker Category',
      'Contract Type distribution', 'Band level breakdown',
      'Job Family Group comparison', 'Blue vs White Collar by Country',
      'Headcount trend by Snapshot Month', 'Top Supervisory Orgs by size',
    ].filter(s_ => !existing.some(e => e.includes(s_.split(' ')[0].toLowerCase()))).slice(0, 6);
  };

  // ─── LANDING ─────────────────────────────────────────────────────────────
  if (showLanding) {
    return (
      <div style={{ height: '100vh', background: 'radial-gradient(ellipse at 25% 15%, #0f3460 0%, #0a2342 50%, #071829 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden', position: 'relative', fontFamily: "'DM Sans',-apple-system,sans-serif" }}>
        <div style={{ position: 'absolute', width: 600, height: 600, borderRadius: '50%', background: 'radial-gradient(circle, #1a6bb520 0%, transparent 70%)', top: -200, right: -100, pointerEvents: 'none' }} />
        <div style={{ maxWidth: 680, width: '100%', padding: '0 24px', position: 'relative', zIndex: 1 }}>
          <div style={{ textAlign: 'center', marginBottom: 44 }}>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 7, background: '#ffffff12', border: '1px solid #ffffff1e', borderRadius: 99, padding: '5px 14px', marginBottom: 24 }}>
              <Sparkles className="w-4 h-4" style={{ color: '#64b5f6' }} />
              <span style={{ fontSize: 12, color: '#90caf9', fontWeight: 500 }}>AI-Powered HR Dashboard Generator</span>
            </div>
            <h1 style={{ fontSize: 42, fontWeight: 800, color: '#f0f7ff', lineHeight: 1.12, letterSpacing: '-1px', marginBottom: 16 }}>
              Transform your HR data<br />
              <span style={{ background: 'linear-gradient(135deg,#64b5f6,#42a5f5)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>into executive insights</span>
            </h1>
            <p style={{ color: '#8fa3b8', fontSize: 15, lineHeight: 1.7, maxWidth: 480, margin: '0 auto' }}>
              Describe what you want to analyze and get a professional dashboard with real charts and insights instantly.
            </p>
          </div>
          <div style={{ background: '#ffffff0c', border: '1px solid #ffffff18', borderRadius: 12, padding: '6px 6px 6px 18px', display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
            <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && input.trim() && createNewChat(input)}
              placeholder="e.g. Analyze attrition trends and identify high-risk groups…"
              style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none', color: '#f0f7ff', fontSize: 14, padding: '9px 0' }} />
            <button onClick={() => input.trim() && createNewChat(input)}
              style={{ padding: '10px 22px', borderRadius: 8, background: '#1a6bb5', color: '#fff', border: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 7, flexShrink: 0 }}>
              <Send className="w-4 h-4" /> Generate
            </button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            {LANDING_PROMPTS.map((p, i) => (
              <button key={i} onClick={() => createNewChat(p.prompt)}
                style={{ background: '#ffffff08', border: '1px solid #ffffff14', borderRadius: 10, padding: '13px 15px', cursor: 'pointer', textAlign: 'left', color: '#cbd5e1', display: 'flex', alignItems: 'flex-start', gap: 10 }}
                onMouseEnter={e => e.currentTarget.style.background = '#ffffff14'}
                onMouseLeave={e => e.currentTarget.style.background = '#ffffff08'}>
                <span style={{ color: '#64b5f6', marginTop: 1, flexShrink: 0 }}>{p.icon}</span>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 3, color: '#e2eaf3' }}>{p.label}</div>
                  <div style={{ fontSize: 11, color: '#5a7a94', lineHeight: 1.4 }}>{p.prompt.slice(0, 72)}…</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // ─── DASHBOARD APP ─────────────────────────────────────────────────────────
  const iconBtn = { background: 'none', border: 'none', cursor: 'pointer', color: theme.textMuted, padding: 4 };
  const sectionLabel = { fontSize: 11, fontWeight: 700, color: theme.sectionTitle, textTransform: 'uppercase', letterSpacing: '0.6px', display: 'flex', alignItems: 'center', gap: 6, marginBottom: 14 };
  const card = { background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 10, boxShadow: '0 1px 3px rgba(0,0,0,0.04)' };
  const altCard = { background: theme.surfaceAlt, border: `1px solid ${theme.border}`, borderRadius: 10, boxShadow: '0 1px 3px rgba(0,0,0,0.04)' };

  return (
    <div style={{ display: 'flex', height: '100vh', background: theme.bg, color: theme.text, fontFamily: "'DM Sans',-apple-system,sans-serif", overflow: 'hidden' }}>

      {/* SIDEBAR */}
      {showSidebar && !presentMode && (
        <div style={{ width: 228, display: 'flex', flexDirection: 'column', background: theme.surface, borderRight: `1px solid ${theme.border}`, flexShrink: 0 }}>
          <div style={{ padding: '15px 14px', borderBottom: `1px solid ${theme.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontSize: 14, fontWeight: 700, color: theme.text, letterSpacing: '-0.3px' }}>Dashboard Agent</div>
              <div style={{ fontSize: 11, color: theme.textMuted, marginTop: 1 }}>HR Analytics AI</div>
            </div>
            <button style={iconBtn} onClick={() => setShowSidebar(false)}><ChevronLeft className="w-4 h-4" /></button>
          </div>
          <button onClick={() => createNewChat()}
            style={{ margin: '10px 10px 5px', padding: '8px 12px', borderRadius: 8, background: theme.accent, color: '#fff', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 7, fontSize: 13, fontWeight: 600 }}>
            <Plus className="w-4 h-4" /> New Dashboard
          </button>
          <div style={{ flex: 1, overflowY: 'auto', padding: '3px 0' }}>
            {chats.map(chat => (
              <div key={chat.id}
                style={{ padding: '8px 12px', margin: '1px 6px', borderRadius: 7, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 7, background: activeChat === chat.id ? theme.accentLight : 'transparent', color: activeChat === chat.id ? theme.accentText : theme.textMuted, fontSize: 13, borderLeft: activeChat === chat.id ? `3px solid ${theme.accent}` : '3px solid transparent' }}
                onClick={() => { setActiveChat(chat.id); setShowLanding(false); }}>
                <LayoutDashboard className="w-3 h-3" style={{ flexShrink: 0, opacity: 0.6 }} />
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{chat.title}</span>
                <button onClick={e => { e.stopPropagation(); deleteChat(chat.id); }} style={{ ...iconBtn, opacity: 0 }}
                  onMouseEnter={e => e.currentTarget.style.opacity = '1'} onMouseLeave={e => e.currentTarget.style.opacity = '0'}>
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>
          <div style={{ borderTop: `1px solid ${theme.border}`, padding: '10px 12px' }}>
            <div style={{ fontSize: 10, color: theme.textMuted, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.5px' }}>Theme</div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {Object.entries(THEMES).map(([key, t]) => (
                <button key={key} title={t.name} onClick={() => setActiveTheme(key)}
                  style={{ width: 22, height: 22, borderRadius: 5, background: t.headerBg, border: activeTheme === key ? `2px solid ${theme.text}` : '2px solid transparent', cursor: 'pointer' }} />
              ))}
            </div>
          </div>
        </div>
      )}

      {/* MAIN */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

        {/* TOP BAR */}
        <div style={{ height: 50, padding: '0 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: `1px solid ${theme.border}`, background: theme.surface, flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {!showSidebar && !presentMode && <button style={iconBtn} onClick={() => setShowSidebar(true)}><ChevronRight className="w-4 h-4" /></button>}
            {!showChat && !presentMode && <button style={iconBtn} onClick={() => setShowChat(true)}><ChevronRight className="w-4 h-4" /></button>}
            <span style={{ fontSize: 14, fontWeight: 600, color: theme.text }}>{dashboard?.title || 'Dashboard'}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {dashboard && (
              <div style={{ position: 'relative' }}>
                <button onClick={() => setShowExportMenu(!showExportMenu)}
                  style={{ padding: '5px 12px', borderRadius: 6, border: `1px solid ${theme.border}`, background: 'transparent', color: theme.textMuted, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, fontWeight: 500 }}>
                  <Download className="w-3.5 h-3.5" /> Export <ChevronDown className="w-3 h-3" />
                </button>
                {showExportMenu && (
                  <div style={{ position: 'absolute', right: 0, top: 36, ...card, minWidth: 160, padding: 6, zIndex: 100, boxShadow: '0 8px 24px rgba(0,0,0,0.12)' }}>
                    {[
                      { icon: <FileText className="w-3.5 h-3.5" />, label: 'Export as PDF', fn: () => { exportToPDF(dashboard, theme); setShowExportMenu(false); } },
                      { icon: <Presentation className="w-3.5 h-3.5" />, label: 'Export as PPTX', fn: () => { handleSuggestionSend('Generate a PowerPoint summary of this dashboard with slide titles and key bullet points for each section'); setShowExportMenu(false); } },
                    ].map((item, i) => (
                      <button key={i} onClick={item.fn} style={{ width: '100%', padding: '7px 11px', background: 'none', border: 'none', color: theme.text, cursor: 'pointer', textAlign: 'left', fontSize: 12, display: 'flex', alignItems: 'center', gap: 8, borderRadius: 7 }}
                        onMouseEnter={e => e.currentTarget.style.background = theme.border} onMouseLeave={e => e.currentTarget.style.background = 'none'}>
                        {item.icon} {item.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
            <button onClick={() => { setPresentMode(!presentMode); if (!presentMode) { setShowChat(false); setShowSidebar(false); } else { setShowChat(true); setShowSidebar(true); } }}
              style={{ padding: '5px 12px', borderRadius: 6, border: `1px solid ${presentMode ? theme.accent : theme.border}`, background: presentMode ? theme.accent : 'transparent', color: presentMode ? '#fff' : theme.textMuted, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, fontWeight: 500 }}>
              {presentMode ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
              {presentMode ? 'Exit' : 'Present'}
            </button>
          </div>
        </div>

        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

          {/* CHAT PANEL */}
          {showChat && !presentMode && (
            <div style={{ width: 296, display: 'flex', flexDirection: 'column', borderRight: `1px solid ${theme.border}`, background: theme.bg, flexShrink: 0 }}>
              <div style={{ padding: '11px 14px', borderBottom: `1px solid ${theme.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: theme.text }}>Chat</span>
                <button style={iconBtn} onClick={() => setShowChat(false)}><ChevronLeft className="w-4 h-4" /></button>
              </div>

              {/* Action chips */}
              {dashboard && (
                <div style={{ padding: '7px 9px', display: 'flex', gap: 5, flexWrap: 'wrap', borderBottom: `1px solid ${theme.border}`, background: theme.surfaceAlt }}>
                  {ACTIONS.map(a => (
                    <button key={a.type} onClick={() => { if (a.type === 'themes') { setShowThemeModal(true); return; } setActionPanel(actionPanel === a.type ? null : a.type); }}
                      style={{ padding: '4px 9px', borderRadius: 99, border: `1px solid ${actionPanel === a.type ? theme.accent : theme.border}`, background: actionPanel === a.type ? theme.accentLight : theme.surface, color: actionPanel === a.type ? theme.accentText : theme.textMuted, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, fontWeight: 500, whiteSpace: 'nowrap' }}>
                      {a.icon} {a.label}
                    </button>
                  ))}
                </div>
              )}

              {actionPanel === 'add_charts' && (
                <div style={{ padding: 9, borderBottom: `1px solid ${theme.border}`, background: theme.surfaceAlt }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: theme.text, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.4px' }}>Select charts to add:</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {getChartSuggestions().map((s_, i) => (
                      <button key={i} onClick={() => { setActionPanel(null); handleSuggestionSend(`Add a chart: ${s_}`); }}
                        style={{ padding: '6px 9px', background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 7, cursor: 'pointer', textAlign: 'left', fontSize: 12, color: theme.text, display: 'flex', alignItems: 'center', gap: 5 }}
                        onMouseEnter={e => e.currentTarget.style.borderColor = theme.accent}
                        onMouseLeave={e => e.currentTarget.style.borderColor = theme.border}>
                        <PlusCircle className="w-3 h-3" style={{ color: theme.accent, flexShrink: 0 }} /> {s_}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {actionPanel === 'add_filters' && (
                <div style={{ padding: 9, borderBottom: `1px solid ${theme.border}`, background: theme.surfaceAlt }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: theme.text, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.4px' }}>Add filter by field:</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                    {['Function','Reporting_Region','Band','Contract_Type','Snapshot_Year','Gender','Blue_White_Collar','Worker_Category'].map((f, i) => {
                      const already = activeFilters.find(af => af.field === f);
                      return (
                        <button key={i} onClick={() => { if (!already) addFilter(f); }}
                          style={{ padding: '4px 9px', background: already ? theme.border : theme.accentLight, border: `1px solid ${already ? theme.border : theme.accent + '50'}`, borderRadius: 99, cursor: already ? 'default' : 'pointer', fontSize: 11, color: already ? theme.textLight : theme.accentText, fontWeight: 500, textDecoration: already ? 'line-through' : 'none' }}>
                          {f} {already ? '✓' : '+'}
                        </button>
                      );
                    })}
                  </div>
                  {activeFilters.length > 0 && (
                    <div style={{ marginTop: 8, fontSize: 11, color: theme.textMuted }}>
                      Active: {activeFilters.map(f => f.field).join(', ')} — visible above dashboard
                    </div>
                  )}
                </div>
              )}

              {actionPanel === 'insights' && (
                <div style={{ padding: 9, borderBottom: `1px solid ${theme.border}`, background: theme.surfaceAlt }}>
                  <button onClick={() => { setActionPanel(null); handleSuggestionSend('Give me 5 deeper key insights from this dashboard with specific numbers, percentages and actionable recommendations'); }}
                    style={{ width: '100%', padding: 8, background: theme.accent, border: 'none', borderRadius: 7, cursor: 'pointer', fontSize: 12, color: '#fff', fontWeight: 600 }}>
                    Generate deeper insights
                  </button>
                </div>
              )}

              <div style={{ flex: 1, overflowY: 'auto', padding: '10px 9px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                {activeChartData?.messages.map((msg, i) => (
                  <div key={i} style={msg.role === 'user'
                    ? { alignSelf: 'flex-end', maxWidth: '88%', background: theme.accent, color: '#fff', padding: '7px 11px', borderRadius: '11px 11px 3px 11px', fontSize: 13, lineHeight: 1.5 }
                    : { alignSelf: 'flex-start', maxWidth: '93%', ...card, color: theme.text, padding: '7px 11px', borderRadius: '3px 11px 11px 11px', fontSize: 13, lineHeight: 1.5 }}>
                    {msg.content}
                  </div>
                ))}
                {loading && (
                  <div style={{ alignSelf: 'flex-start', ...card, padding: '9px 12px', borderRadius: '3px 11px 11px 11px' }}>
                    <div style={{ display: 'flex', gap: 4, marginBottom: genStep ? 6 : 0 }}>
                      {[0,1,2].map(i => <div key={i} style={{ width: 6, height: 6, borderRadius: '50%', background: theme.accent, animation: 'pulse 1.2s infinite', animationDelay: `${i*0.2}s` }} />)}
                      <style>{`@keyframes pulse{0%,80%,100%{transform:scale(.6);opacity:.4}40%{transform:scale(1);opacity:1}}`}</style>
                    </div>
                    {genStep && <div style={{ fontSize: 11, color: theme.textMuted }}>{genStep}</div>}
                  </div>
                )}
                {suggestions.length > 0 && !loading && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 2 }}>
                    <div style={{ fontSize: 10, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: '0.4px' }}>Try these next:</div>
                    {suggestions.slice(0, 4).map((s_, i) => (
                      <button key={i} onClick={() => handleSuggestionSend(s_)}
                        style={{ padding: '6px 10px', background: theme.accentLight, border: `1px solid ${theme.accent}28`, borderRadius: 7, cursor: 'pointer', textAlign: 'left', fontSize: 12, color: theme.accentText, fontWeight: 500 }}>
                        {s_}
                      </button>
                    ))}
                  </div>
                )}
                <div ref={msgEndRef} />
              </div>

              <div style={{ padding: '9px', borderTop: `1px solid ${theme.border}` }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 9, padding: '5px 5px 5px 10px' }}>
                  <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && !loading && handleSend()}
                    placeholder={loading ? 'Generating…' : 'Ask about the dashboard…'} disabled={loading}
                    style={{ flex: 1, border: 'none', background: 'transparent', outline: 'none', fontSize: 13, color: theme.text }} />
                  <button onClick={handleSend} disabled={!input.trim() || loading}
                    style={{ width: 29, height: 29, borderRadius: 7, border: 'none', background: input.trim() && !loading ? theme.accent : theme.border, color: input.trim() && !loading ? '#fff' : theme.textMuted, cursor: input.trim() && !loading ? 'pointer' : 'default', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    <Send className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* DASHBOARD PANEL */}
          <div style={{ flex: 1, overflowY: 'auto', background: theme.bg }} onClick={() => openFilterDropdown && setOpenFilterDropdown(null)}>
            {dashboard ? (
              <div style={{ maxWidth: 1140, margin: '0 auto', padding: '26px 26px 48px' }}>

                {/* ── TITLE BANNER ── */}
                <div style={{ background: theme.headerBg, borderRadius: 14, padding: '26px 36px', marginBottom: 14, textAlign: 'center', boxShadow: '0 4px 20px rgba(10,35,66,0.18)' }}>
                  <h1 style={{ margin: 0, fontSize: 24, fontWeight: 800, color: '#ffffff', letterSpacing: '-0.3px', lineHeight: 1.2 }}>
                    {dashboard.title}
                  </h1>
                </div>

                {/* ── OVERVIEW CARD ── */}
                {dashboard.overview && (
                  <div style={{ ...card, padding: '18px 24px', marginBottom: 18 }}>
                    <div style={{ fontSize: 10, fontWeight: 700, color: theme.sectionTitle, textTransform: 'uppercase', letterSpacing: '0.6px', marginBottom: 8 }}>Overview</div>
                    <p style={{ margin: 0, color: theme.textMuted, fontSize: 14, lineHeight: 1.75 }}>{dashboard.overview}</p>
                  </div>
                )}

                {/* ── ACTIVE FILTER BAR ── */}
                {activeFilters.length > 0 && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 18, flexWrap: 'wrap' }} onClick={e => e.stopPropagation()}>
                    <span style={{ fontSize: 11, fontWeight: 600, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: '0.5px' }}>Filters:</span>
                    {activeFilters.map(f => (
                      <div key={f.field} style={{ position: 'relative' }}>
                        <button onClick={() => setOpenFilterDropdown(openFilterDropdown === f.field ? null : f.field)}
                          style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '5px 10px', borderRadius: 6, border: `1px solid ${theme.border}`, background: theme.surface, color: theme.text, cursor: 'pointer', fontSize: 12, fontWeight: 500, boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
                          <Trash2 className="w-3 h-3" style={{ color: theme.textMuted, cursor: 'pointer' }} onClick={e => { e.stopPropagation(); removeFilter(f.field); }} />
                          {f.field}
                          <span style={{ background: theme.accent, color: '#fff', borderRadius: 99, padding: '1px 6px', fontSize: 10, fontWeight: 700 }}>
                            {f.selected.length === f.options.length ? `All (${f.options.length})` : f.selected.length}
                          </span>
                          <ChevronDown className="w-3 h-3" style={{ color: theme.textMuted }} />
                        </button>
                        {openFilterDropdown === f.field && (
                          <div style={{ position: 'absolute', top: 36, left: 0, ...card, minWidth: 210, padding: 8, zIndex: 200, boxShadow: '0 8px 28px rgba(0,0,0,0.16)' }} onClick={e => e.stopPropagation()}>
                            <button onClick={() => toggleAllFilter(f.field)}
                              style={{ width: '100%', padding: '7px 10px', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', fontSize: 12, color: theme.accent, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8, borderRadius: 6, marginBottom: 4 }}
                              onMouseEnter={e => e.currentTarget.style.background = theme.accentLight}
                              onMouseLeave={e => e.currentTarget.style.background = 'none'}>
                              <div style={{ width: 15, height: 15, borderRadius: 3, background: f.selected.length === f.options.length ? theme.accent : 'transparent', border: `2px solid ${theme.accent}`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                                {f.selected.length === f.options.length && <Check style={{ width: 9, height: 9, color: '#fff' }} />}
                              </div>
                              {f.selected.length === f.options.length ? `Deselect All (${f.options.length})` : `Select All (${f.options.length})`}
                            </button>
                            {f.options.map(opt => {
                              const checked = f.selected.includes(opt);
                              return (
                                <button key={opt} onClick={() => toggleFilterOption(f.field, opt)}
                                  style={{ width: '100%', padding: '7px 10px', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', fontSize: 13, color: theme.text, display: 'flex', alignItems: 'center', gap: 8, borderRadius: 6 }}
                                  onMouseEnter={e => e.currentTarget.style.background = theme.surfaceAlt}
                                  onMouseLeave={e => e.currentTarget.style.background = 'none'}>
                                  <div style={{ width: 15, height: 15, borderRadius: 3, background: checked ? theme.accent : 'transparent', border: `2px solid ${checked ? theme.accent : theme.border}`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                                    {checked && <Check style={{ width: 9, height: 9, color: '#fff' }} />}
                                  </div>
                                  {opt}
                                </button>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {/* KPI Cards */}
                {dashboard.metrics?.length > 0 && (
                  <div style={{ marginBottom: 26 }}>
                    <div style={sectionLabel}><BarChart3 className="w-3.5 h-3.5" /> Key Metrics</div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 14 }}>
                      {dashboard.metrics.map((m, i) => (
                        <div key={i} style={{ ...card, padding: '18px 20px' }}>
                          <div style={{ fontSize: 11, fontWeight: 600, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 8 }}>{m.label}</div>
                          <div style={{ fontSize: 28, fontWeight: 700, color: theme.kpiAccent, letterSpacing: '-0.5px', marginBottom: 7 }}>{m.value}</div>
                          <TrendBadge trend={m.trend} change={m.change} theme={theme} />
                          {m.insight && <div style={{ fontSize: 12, color: theme.textMuted, marginTop: 8, lineHeight: 1.5 }}>{m.insight}</div>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Overall Insights */}
                {dashboard.overall_insights?.length > 0 && (
                  <div style={{ marginBottom: 26 }}>
                    <div style={sectionLabel}><Lightbulb className="w-3.5 h-3.5" /> Overall Insights</div>
                    <div style={{ ...card, padding: '16px 20px' }}>
                      {dashboard.overall_insights.map((ins, i) => (
                        <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, padding: '4px 0', fontSize: 13, color: theme.textMuted, lineHeight: 1.65 }}>
                          <span style={{ color: theme.accent, fontWeight: 700, flexShrink: 0, lineHeight: 1.65 }}>•</span>
                          <span>{ins}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Visualizations — BRICK AI STYLE: chart + insights side by side */}
                {dashboard.visualizations?.length > 0 && (
                  <div>
                    <div style={sectionLabel}><BarChart3 className="w-3.5 h-3.5" /> Visualizations</div>

                    {dashboard.visualizations.map((viz, i) => {
                      const hasInsights = viz.key_insights?.length > 0;
                      // Alternate: even = chart|insights, odd = insights|chart
                      const flipped = i % 2 === 1;
                      const chartBlock = (
                        <div style={{ ...card, padding: '18px 20px' }}>
                          <div style={{ fontSize: 14, fontWeight: 700, color: theme.text, marginBottom: 4 }}>{viz.title}</div>
                          {viz.description && <div style={{ fontSize: 12, color: theme.textMuted, marginBottom: 14, lineHeight: 1.5 }}>{viz.description}</div>}
                          {renderChart(viz, theme)}
                        </div>
                      );
                      const insightsBlock = hasInsights ? (
                        <div style={{ ...altCard, padding: '18px 20px', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                          <div style={{ fontSize: 12, fontWeight: 700, color: theme.sectionTitle, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
                            <Lightbulb className="w-3.5 h-3.5" /> Key Insights
                          </div>
                          {viz.key_insights.slice(0, 3).map((ins, j) => (
                            <div key={j} style={{ display: 'flex', alignItems: 'flex-start', gap: 7, padding: '5px 0', fontSize: 13, color: theme.textMuted, lineHeight: 1.65 }}>
                              <span style={{ color: theme.accent, fontWeight: 700, flexShrink: 0 }}>•</span>
                              <span>{ins}</span>
                            </div>
                          ))}
                        </div>
                      ) : <div />;

                      return (
                        <div key={viz.id || `v-${i}`} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
                          {flipped ? <>{insightsBlock}{chartBlock}</> : <>{chartBlock}{insightsBlock}</>}
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Recommendations */}
                {dashboard.recommendations?.length > 0 && (
                  <div style={{ marginTop: 20 }}>
                    <div style={{ ...sectionLabel, color: theme.positive }}><Check className="w-3.5 h-3.5" style={{ color: theme.positive }} /> Recommendations</div>
                    <div style={{ ...card, padding: '16px 20px' }}>
                      {dashboard.recommendations.map((rec, i) => (
                        <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, padding: '4px 0', fontSize: 13, color: theme.textMuted, lineHeight: 1.65 }}>
                          <span style={{ color: theme.positive, fontWeight: 700, flexShrink: 0 }}>✓</span>
                          <span>{rec}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 12 }}>
                <LayoutDashboard style={{ width: 40, height: 40, color: theme.border }} />
                <div style={{ color: theme.textMuted, fontSize: 14 }}>Start a conversation to generate your dashboard</div>
                <button onClick={() => setShowLanding(true)} style={{ fontSize: 12, color: theme.accent, background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}>Back to home</button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* THEME MODAL */}
      {showThemeModal && (
        <div style={{ position: 'fixed', inset: 0, background: '#00000050', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setShowThemeModal(false)}>
          <div style={{ ...card, padding: 24, minWidth: 400, boxShadow: '0 20px 60px rgba(0,0,0,0.25)' }} onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
              <span style={{ fontSize: 15, fontWeight: 700, color: theme.text }}>Choose Theme</span>
              <button style={iconBtn} onClick={() => setShowThemeModal(false)}><X className="w-4 h-4" /></button>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
              {Object.entries(THEMES).map(([key, t]) => (
                <button key={key} onClick={() => { setActiveTheme(key); setShowThemeModal(false); }}
                  style={{ padding: '14px 12px', borderRadius: 10, border: `2px solid ${activeTheme === key ? t.accent : theme.border}`, background: t.bg, cursor: 'pointer', textAlign: 'center' }}>
                  <div style={{ width: 36, height: 12, borderRadius: 3, background: t.headerBg, margin: '0 auto 8px' }} />
                  <div style={{ display: 'flex', gap: 4, justifyContent: 'center', marginBottom: 7 }}>
                    {t.colors.slice(0, 4).map((c, i) => <div key={i} style={{ width: 10, height: 10, borderRadius: 2, background: c }} />)}
                  </div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: t.text }}>{t.name}</div>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default DashboardAgent;