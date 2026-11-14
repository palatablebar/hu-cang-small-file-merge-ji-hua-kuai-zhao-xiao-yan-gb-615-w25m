/** 无框架 UI 组件：表格 / 徽标 / 抽屉 / 空态 / 统计条 / 图表 / toast / 标签页。 */

export function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

export function fmtTime(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return esc(iso);
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

export function fmtBytes(bytes) {
  if (bytes === null || bytes === undefined) return '—';
  const value = Number(bytes);
  if (!Number.isFinite(value)) return '—';
  if (value >= 1024 ** 4) return `${(value / 1024 ** 4).toFixed(2)} TiB`;
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(2)} GiB`;
  if (value >= 1024 ** 2) return `${(value / 1024 ** 2).toFixed(1)} MiB`;
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${value} B`;
}

export function fmtPct(ratio, digits = 1) {
  if (ratio === null || ratio === undefined) return '—';
  return `${(Number(ratio) * 100).toFixed(digits)}%`;
}

export function fmtInt(value) {
  if (value === null || value === undefined) return '—';
  return new Intl.NumberFormat('zh-CN').format(Number(value));
}

export function badge(tone, text) {
  return `<span class="badge ${esc(tone)}">${esc(text)}</span>`;
}

export function chips(items) {
  return `<div class="chips">${items.map((item) => `<span class="chip ${esc(item.tone || '')}">${esc(item.text)}</span>`).join('')}</div>`;
}

export function meter(ratio, tone = '') {
  const width = Math.max(0, Math.min(100, Math.round((Number(ratio) || 0) * 100)));
  return `<div class="meter ${esc(tone)}"><span style="width:${width}%"></span></div>`;
}

export function statStrip(items) {
  return `<div class="stat-strip">${items
    .map(
      (item) => `<div class="stat">
        <span class="k">${esc(item.label)}</span>
        <span class="v">${esc(item.value)}</span>
        <span class="hint">${esc(item.hint || '')}</span>
      </div>`,
    )
    .join('')}</div>`;
}

export function emptyState({ title, hint, actionText, actionId }) {
  return `<div class="empty" data-testid="empty-state">
    <div class="mark">${esc(title)}</div>
    <p>${esc(hint || '')}</p>
    ${actionText ? `<button class="btn ghost" id="${esc(actionId || 'empty-action')}">${esc(actionText)}</button>` : ''}
  </div>`;
}

export function errorBox(message, retryId = 'retry-btn') {
  return `<div class="error-box"><span>${esc(message)}</span><button class="btn sm ghost" id="${esc(retryId)}">重试</button></div>`;
}

export function notice({ tone = '', title, body }) {
  return `<div class="notice ${esc(tone)}">${title ? `<b>${esc(title)}</b>` : ''}<span>${body}</span></div>`;
}

export function table({ columns, rows, rowId, empty }) {
  if (!rows || rows.length === 0) return emptyState(empty || { title: '暂无记录', hint: '调整筛选条件，或先扫描一次 manifest。' });
  const head = columns.map((col) => `<th>${esc(col.label)}</th>`).join('');
  const body = rows
    .map(
      (row) => `<tr data-id="${esc(row.id ?? row.key)}" ${rowId ? `id="${esc(rowId(row))}"` : ''}>
        ${columns.map((col) => `<td class="${esc(col.className || '')}" data-col="${esc(col.key || '')}">${col.render ? col.render(row) : esc(row[col.key])}</td>`).join('')}
      </tr>`,
    )
    .join('');
  return `<div class="table-wrap"><table class="data"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

export function drawer({ title, subtitle, body, footer, wide = false }) {
  const backdrop = document.createElement('div');
  backdrop.className = 'drawer-backdrop';
  backdrop.innerHTML = `<aside class="drawer" role="dialog" aria-modal="true" ${wide ? 'style="width:min(760px,94vw)"' : ''}>
    <div class="drawer-head">
      <div>
        <h2>${esc(title)}</h2>
        <div class="mono muted">${esc(subtitle || '')}</div>
      </div>
      <button class="btn sm ghost" data-close>关闭</button>
    </div>
    <div class="drawer-body">${body}</div>
    ${footer ? `<div class="drawer-foot">${footer}</div>` : ''}
  </aside>`;
  const close = () => {
    backdrop.remove();
    document.removeEventListener('keydown', onKey);
  };
  const onKey = (event) => {
    if (event.key === 'Escape') close();
  };
  backdrop.addEventListener('click', (event) => {
    if (event.target === backdrop || event.target.closest('[data-close]')) close();
  });
  document.addEventListener('keydown', onKey);
  document.body.appendChild(backdrop);
  return { root: backdrop, close };
}

export function kv(items) {
  return `<dl class="kv">${items
    .map(([key, value]) => `<dt>${esc(key)}</dt><dd>${value === undefined || value === null || value === '' ? '—' : value}</dd>`)
    .join('')}</dl>`;
}

export function barList(items, tone = '') {
  const max = Math.max(1, ...items.map((item) => item.count));
  return `<div class="bars">${items
    .map(
      (item) => `<div class="bar-row">
        <span>${esc(item.label)}</span>
        <div class="bar-track"><div class="bar-fill ${esc(tone)}" style="width:${Math.round((item.count / max) * 100)}%"></div></div>
        <span class="mono">${esc(item.count)}</span>
      </div>`,
    )
    .join('')}</div>`;
}

export function field({ label, name, type = 'text', value = '', placeholder = '', options = null, attrs = '' }) {
  const control = options
    ? `<select name="${esc(name)}" id="${esc(name)}" ${attrs}>${options
        .map((opt) => `<option value="${esc(opt.value)}" ${String(opt.value) === String(value) ? 'selected' : ''}>${esc(opt.label)}</option>`)
        .join('')}</select>`
    : `<input name="${esc(name)}" id="${esc(name)}" type="${esc(type)}" value="${esc(value)}" placeholder="${esc(placeholder)}" ${attrs} />`;
  return `<div class="field"><label for="${esc(name)}">${esc(label)}</label>${control}</div>`;
}

export function tabs({ items, active }) {
  return `<div class="tabs" role="tablist">${items
    .map(
      (item) =>
        `<button class="tab ${item.key === active ? 'active' : ''}" data-tab="${esc(item.key)}" role="tab">${esc(item.label)}</button>`,
    )
    .join('')}</div>`;
}

export function toast(message, tone = '') {
  const stack = document.getElementById('toast-stack');
  const node = document.createElement('div');
  node.className = `toast ${tone}`;
  node.textContent = message;
  stack.appendChild(node);
  setTimeout(() => node.remove(), 3600);
}

export function errorMessage(err) {
  if (!err) return '未知错误';
  if (err.code === 'FORBIDDEN') return '当前角色没有这个操作的权限';
  return err.message || '请求失败';
}
