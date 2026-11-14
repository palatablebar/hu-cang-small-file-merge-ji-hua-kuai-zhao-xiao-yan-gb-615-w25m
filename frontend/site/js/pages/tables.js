import { api } from '../api.js';
import { ENUMS, can } from '../config.js';
import { drawer, emptyState, errorBox, errorMessage, esc, field, fmtBytes, fmtInt, fmtPct, fmtTime, kv, table, toast } from '../ui.js';

const state = { q: '', layer: '', enabled: '' };

function partitionTable(rows) {
  if (!rows || rows.length === 0) return emptyState({ title: '该表还没有分区', hint: '扫描 manifest 后分区会自动出现。' });
  return `<div class="table-wrap"><table class="data" style="min-width:0">
    <thead><tr><th>分区</th><th>文件</th><th>小文件</th><th>delete</th><th>体积</th><th>行数</th><th>标记</th></tr></thead>
    <tbody>${rows
      .map(
        (row) => `<tr>
          <td class="mono">${esc(row.partition_key)}</td>
          <td class="num">${fmtInt(row.file_count)}</td>
          <td class="num">${fmtInt(row.small_file_count)}</td>
          <td class="num">${fmtInt(row.delete_file_count)}</td>
          <td class="num">${fmtBytes(row.total_bytes)}</td>
          <td class="num">${fmtInt(row.total_rows)}</td>
          <td>${row.needs_rewrite ? '<span class="badge danger">待 rewrite</span>' : '<span class="muted">—</span>'}</td>
        </tr>`,
      )
      .join('')}</tbody></table></div>`;
}

async function openTable(view, ctx, item) {
  let partitions = [];
  try {
    const data = await api.get('/api/partitions', { table_id: item.id, limit: 18 });
    partitions = data.items;
  } catch (err) {
    toast(errorMessage(err), 'err');
  }
  const stats = item.stats || {};
  const { root } = drawer({
    title: item.name,
    subtitle: `${item.code} · ${item.fmt_label} · ${item.layer_label}`,
    wide: true,
    body: `${kv([
      ['库表位置', `<span class="mono">${esc(item.location)}</span>`],
      ['分区规格', `<span class="mono">${esc(item.partition_spec)}</span>`],
      ['目标文件大小', `${esc(item.target_mb)} MB`],
      ['最小文件数', esc(item.min_files)],
      ['流读窗口', `<span class="mono">${esc(item.stream_window_start)} – ${esc(item.stream_window_end)}</span>`],
      ['流读延迟', `${fmtInt(item.flow_lag_seconds)} 秒`],
      ['负责人', esc(item.owner)],
      ['最近扫描', fmtTime(item.last_scanned_at)],
      ['规模', `分区 ${fmtInt(stats.partitions)} · 文件 ${fmtInt(stats.files)} · 小文件 ${fmtPct(
        stats.files ? (stats.small_files || 0) / stats.files : 0,
      )}`],
      ['备注', esc(item.note || '—')],
    ])}
    <h3 style="margin:16px 0 8px;font-size:0.95rem">分区明细（前 18 个）</h3>
    ${partitionTable(partitions)}`,
    footer: `<button class="btn ghost" data-plans>看这个表的合并计划</button>`,
  });
  root.querySelector('[data-plans]')?.addEventListener('click', () => {
    location.hash = '#/plans';
  });
}

function openCreate(view, ctx) {
  const { root, close } = drawer({
    title: '登记湖表',
    subtitle: '登记后即可扫描 manifest 并生成合并计划',
    body: `<form id="table-form" style="display:grid;gap:12px">
      <div class="inline-fields">
        ${field({ label: '表编码（小写+下划线）', name: 'code', placeholder: 'dwd_order_ext' })}
        ${field({ label: '表名', name: 'name', placeholder: '订单扩展明细 DWD' })}
      </div>
      <div class="inline-fields">
        ${field({ label: '分层', name: 'layer', value: 'dwd', options: Object.entries(ENUMS.layer).map(([value, label]) => ({ value, label })) })}
        ${field({ label: '表格式', name: 'fmt', value: 'iceberg', options: Object.entries(ENUMS.fmt).map(([value, label]) => ({ value, label })) })}
      </div>
      <div class="inline-fields">
        ${field({ label: '目标文件 MB', name: 'target_mb', type: 'number', value: '128', attrs: 'min="1" max="1024"' })}
        ${field({ label: '每分区最小文件数', name: 'min_files', type: 'number', value: '5', attrs: 'min="2" max="100"' })}
        ${field({ label: '流读延迟（秒）', name: 'flow_lag_seconds', type: 'number', value: '900', attrs: 'min="0" max="7200"' })}
      </div>
      <div class="inline-fields">
        ${field({ label: '流读窗口开始', name: 'stream_window_start', value: '00:00', placeholder: '00:00' })}
        ${field({ label: '流读窗口结束', name: 'stream_window_end', value: '06:30', placeholder: '06:30' })}
      </div>
      ${field({ label: '备注', name: 'note', placeholder: '上游 Flink 每小时落盘' })}
      <div class="form-error" id="table-error"></div>
      <button class="btn accent" type="submit">保存并登记</button>
    </form>`,
  });
  root.querySelector('#table-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.target;
    const button = form.querySelector('button[type=submit]');
    button.disabled = true;
    try {
      await api.post('/api/tables', {
        code: form.code.value.trim(),
        name: form.name.value.trim(),
        layer: form.layer.value,
        fmt: form.fmt.value,
        target_bytes: Math.round(Number(form.target_mb.value) * 1024 * 1024),
        min_files: Number(form.min_files.value),
        flow_lag_seconds: Number(form.flow_lag_seconds.value),
        stream_window_start: form.stream_window_start.value,
        stream_window_end: form.stream_window_end.value,
        note: form.note.value.trim() || null,
      });
      toast('湖表已登记');
      close();
      await tablesPage.render(view, ctx);
    } catch (err) {
      root.querySelector('#table-error').textContent =
        err.code === 'CONFLICT' ? '表编码已存在' : err.code === 'VALIDATION' ? '参数不合法（编码需小写字母开头）' : errorMessage(err);
      button.disabled = false;
    }
  });
}

export const tablesPage = {
  async render(view, ctx) {
    let data;
    try {
      data = await api.get('/api/tables', { q: state.q, layer: state.layer, enabled: state.enabled, limit: 30 });
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => tablesPage.render(view, ctx));
      return;
    }
    view.innerHTML = `
      <section class="panel">
        <div class="panel-head">
          <h2>表与分区</h2>
          <div style="display:flex;gap:8px;align-items:center">
            <span class="meta">${data.total} 张湖表 · 小文件阈值 ${fmtBytes(data.small_file_threshold)}</span>
            ${can(ctx.user.role, 'table:write') ? '<button class="btn sm accent" id="new-table">登记湖表</button>' : ''}
          </div>
        </div>
        <div class="panel-body">
          <div class="filter-bar" id="table-filters">
            ${field({ label: '搜索', name: 'q', value: state.q, placeholder: '表名 / 编码' })}
            ${field({
              label: '分层',
              name: 'layer',
              value: state.layer,
              options: [{ value: '', label: '全部' }, ...Object.entries(ENUMS.layer).map(([value, label]) => ({ value, label }))],
            })}
            ${field({ label: '状态', name: 'enabled', value: state.enabled, options: [{ value: '', label: '全部' }, { value: 'true', label: '启用' }, { value: 'false', label: '停用' }] })}
            <div class="spacer"></div>
          </div>
        </div>
        ${table({
          rows: data.items,
          empty: { title: '还没有登记湖表', hint: '管理员登记第一张表后，扫描 manifest 就能看到分区。' },
          columns: [
            {
              key: 'code',
              label: '湖表',
              render: (row) => `<b class="mono">${esc(row.code)}</b><div class="muted">${esc(row.name)}</div>`,
            },
            { key: 'layer_label', label: '分层' },
            { key: 'fmt_label', label: '格式' },
            { key: 'stats.partitions', label: '分区', className: 'num', render: (row) => fmtInt(row.stats?.partitions) },
            { key: 'stats.files', label: '文件', className: 'num', render: (row) => fmtInt(row.stats?.files) },
            {
              key: 'stats.small_files',
              label: '小文件',
              className: 'num',
              render: (row) => `${fmtInt(row.stats?.small_files)}<span class="muted"> · ${fmtPct(
                row.stats?.files ? (row.stats.small_files || 0) / row.stats.files : 0,
              )}</span>`,
            },
            {
              key: 'stats.needs_rewrite_partitions',
              label: '待 rewrite',
              className: 'num',
              render: (row) =>
                row.stats?.needs_rewrite_partitions
                  ? `<span class="badge danger">${esc(row.stats.needs_rewrite_partitions)} 个分区</span>`
                  : '<span class="muted">—</span>',
            },
            { key: 'target_mb', label: '目标 MB', className: 'num' },
            {
              key: 'stream_window',
              label: '流读窗口',
              render: (row) => `<span class="mono">${esc(row.stream_window_start)}–${esc(row.stream_window_end)}</span>`,
            },
          ],
        })}
      </section>`;

    const filters = view.querySelector('#table-filters');
    filters?.addEventListener('change', () => {
      state.q = filters.querySelector('[name=q]').value.trim();
      state.layer = filters.querySelector('[name=layer]').value;
      state.enabled = filters.querySelector('[name=enabled]').value;
      tablesPage.render(view, ctx);
    });
    filters?.querySelector('[name=q]')?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        state.q = event.target.value.trim();
        tablesPage.render(view, ctx);
      }
    });
    view.querySelectorAll('table.data tbody tr').forEach((row) => {
      row.addEventListener('click', () => {
        const item = data.items.find((entry) => String(entry.id) === row.dataset.id);
        if (item) openTable(view, ctx, item);
      });
    });
    view.querySelector('#new-table')?.addEventListener('click', () => openCreate(view, ctx));
  },
};

export default tablesPage;
