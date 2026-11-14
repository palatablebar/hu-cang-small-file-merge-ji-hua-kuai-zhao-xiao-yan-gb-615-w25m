import { api } from '../api.js';
import { ENUMS, can } from '../config.js';
import { drawer, errorBox, errorMessage, esc, field, fmtBytes, fmtInt, fmtTime, kv, table, toast } from '../ui.js';

const state = { tableId: '', kind: '', smallOnly: false, q: '', offset: 0, limit: 20 };

function openFile(view, ctx, item) {
  drawer({
    title: item.path.split('/').pop(),
    subtitle: item.path,
    wide: true,
    body: `${kv([
      ['湖表', `${esc(item.table_code)} · ${esc(item.table_name)}`],
      ['分区', `<span class="mono">${esc(item.partition_key)}</span>`],
      ['类型', `<span class="badge ${item.kind === 'delete' ? 'danger' : 'info'}">${esc(item.kind_label)}</span>`],
      ['大小', `${fmtBytes(item.bytes)}（${esc(item.mb)} MB）`],
      ['行数', fmtInt(item.rows)],
      ['校验和', `<span class="mono">${esc(item.checksum)}</span>`],
      ['是否小文件', item.is_small ? '<span class="badge warn">是</span>' : '<span class="muted">否</span>'],
      ['提交时间', fmtTime(item.committed_at)],
    ])}
    <h3 style="margin:14px 0 8px;font-size:0.95rem">manifest 原文</h3>
    <pre class="code">${esc(
      JSON.stringify(
        {
          path: item.path,
          partition: item.partition_key,
          kind: item.kind,
          bytes: item.bytes,
          rows: item.rows,
          checksum: item.checksum,
        },
        null,
        2,
      ),
    )}</pre>`,
  });
}

async function rescan(view, ctx) {
  try {
    const result = await api.post('/api/files/scan', state.tableId ? { table_id: Number(state.tableId) } : {});
    toast(`扫描完成：${result.tables} 张表 / ${result.partitions} 分区 / ${result.files} 文件`);
    await filesPage.render(view, ctx);
  } catch (err) {
    toast(errorMessage(err), 'err');
  }
}

export const filesPage = {
  async render(view, ctx) {
    let tables;
    let data;
    try {
      [tables, data] = await Promise.all([
        api.get('/api/tables', { limit: 50 }),
        api.get('/api/files', {
          table_id: state.tableId,
          kind: state.kind,
          small_only: state.smallOnly,
          q: state.q,
          limit: state.limit,
          offset: state.offset,
        }),
      ]);
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => filesPage.render(view, ctx));
      return;
    }
    const pages = Math.max(1, Math.ceil(data.total / state.limit));
    const page = Math.floor(state.offset / state.limit) + 1;
    view.innerHTML = `
      <section class="panel">
        <div class="panel-head">
          <h2>文件清单</h2>
          <div style="display:flex;gap:8px;align-items:center">
            <span class="meta">${fmtInt(data.total)} 个文件 · 小文件阈值 ${fmtBytes(data.small_file_threshold)}</span>
            ${can(ctx.user.role, 'file:scan') ? '<button class="btn sm ghost" id="rescan">重扫 manifest</button>' : ''}
          </div>
        </div>
        <div class="panel-body">
          <div class="filter-bar" id="file-filters">
            ${field({
              label: '湖表',
              name: 'table_id',
              value: state.tableId,
              options: [{ value: '', label: '全部' }, ...tables.items.map((item) => ({ value: item.id, label: item.code }))],
            })}
            ${field({
              label: '文件类型',
              name: 'kind',
              value: state.kind,
              options: [{ value: '', label: '全部' }, ...Object.entries(ENUMS.fileKind).map(([value, label]) => ({ value, label }))],
            })}
            ${field({
              label: '只看小文件',
              name: 'small_only',
              value: state.smallOnly ? 'true' : '',
              options: [{ value: '', label: '否' }, { value: 'true', label: '是' }],
            })}
            ${field({ label: '搜索路径', name: 'q', value: state.q, placeholder: 'part- / hour=' })}
            <div class="spacer"></div>
          </div>
        </div>
        ${table({
          rows: data.items,
          empty: { title: '这个筛选下没有文件', hint: '换湖表或清空搜索词再看。' },
          columns: [
            {
              key: 'path',
              label: '文件路径',
              render: (row) => `<span class="mono">${esc(row.path.split('/').slice(-2).join('/'))}</span>`,
            },
            { key: 'partition_key', label: '分区', className: 'mono' },
            {
              key: 'kind',
              label: '类型',
              render: (row) => `<span class="badge ${row.kind === 'delete' ? 'danger' : 'info'}">${esc(row.kind_label)}</span>`,
            },
            { key: 'mb', label: '大小 MB', className: 'num' },
            { key: 'rows', label: '行数', className: 'num', render: (row) => fmtInt(row.rows) },
            { key: 'checksum', label: '校验和', className: 'mono' },
            { key: 'is_small', label: '小文件', render: (row) => (row.is_small ? '<span class="badge warn">是</span>' : '<span class="muted">否</span>') },
          ],
        })}
        <div class="panel-body" style="display:flex;justify-content:space-between;align-items:center">
          <span class="mono muted">第 ${page} / ${pages} 页</span>
          <span style="display:flex;gap:8px">
            <button class="btn sm ghost" id="prev-page" ${state.offset === 0 ? 'disabled' : ''}>上一页</button>
            <button class="btn sm ghost" id="next-page" ${state.offset + state.limit >= data.total ? 'disabled' : ''}>下一页</button>
          </span>
        </div>
      </section>`;

    const filters = view.querySelector('#file-filters');
    filters?.addEventListener('change', () => {
      state.tableId = filters.querySelector('[name=table_id]').value;
      state.kind = filters.querySelector('[name=kind]').value;
      state.smallOnly = filters.querySelector('[name=small_only]').value === 'true';
      state.q = filters.querySelector('[name=q]').value.trim();
      state.offset = 0;
      filesPage.render(view, ctx);
    });
    filters?.querySelector('[name=q]')?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        state.q = event.target.value.trim();
        state.offset = 0;
        filesPage.render(view, ctx);
      }
    });
    view.querySelector('#prev-page')?.addEventListener('click', () => {
      state.offset = Math.max(0, state.offset - state.limit);
      filesPage.render(view, ctx);
    });
    view.querySelector('#next-page')?.addEventListener('click', () => {
      state.offset += state.limit;
      filesPage.render(view, ctx);
    });
    view.querySelector('#rescan')?.addEventListener('click', () => rescan(view, ctx));
    view.querySelectorAll('table.data tbody tr').forEach((row) => {
      row.addEventListener('click', () => {
        const item = data.items.find((entry) => String(entry.id) === row.dataset.id);
        if (item) openFile(view, ctx, item);
      });
    });
  },
};

export default filesPage;
