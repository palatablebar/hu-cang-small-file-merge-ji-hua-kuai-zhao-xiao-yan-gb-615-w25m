import { api } from '../api.js';
import { ENUMS, can, verdictTone } from '../config.js';
import {
  drawer,
  emptyState,
  errorBox,
  errorMessage,
  esc,
  field,
  fmtBytes,
  fmtInt,
  fmtTime,
  kv,
  notice,
  table,
  tabs,
  toast,
} from '../ui.js';

const state = { tab: 'verify', tableId: '', verdict: '', audit: null };

function verdictNotice(verdict, reasons, rowsDelta) {
  const tone = verdict === 'consistent' ? 'ok' : verdict === 'lossy' ? 'danger' : 'warn';
  const titles = {
    consistent: '守恒一致：行数与校验和都能对上',
    lossy: '不守恒：这次合并丢了数据',
    unverifiable: '不可判定：缺少 checksum 或 manifest',
  };
  return notice({
    tone,
    title: titles[verdict] || '未校验',
    body: `原因 ${esc((reasons || []).join(', ') || '—')}${rowsDelta !== undefined && rowsDelta !== null ? ` · 行数差 ${esc(rowsDelta)}` : ''}`,
  });
}

async function openPair(view, ctx, item) {
  let result = null;
  if (can(ctx.user.role, 'snapshot:verify') && item.before_id && item.after_id) {
    try {
      result = await api.post('/api/snapshots/verify', { before_id: item.before_id, after_id: item.after_id });
    } catch (err) {
      toast(errorMessage(err), 'err');
    }
  }
  const stored = (item.after && item.after.verify) || {};
  const detail = result || stored;
  const rewritten = (detail.rewritten || []).slice(0, 8);
  const body = `
    ${verdictNotice(detail.verdict || item.verdict || 'unverifiable', detail.reasons || item.reasons, detail.rows_delta ?? item.rows_delta)}
    ${kv([
      ['湖表', `${esc(item.table_code)} · ${esc(item.table_name)}`],
      ['快照序号', esc(item.seq_no)],
      ['合并前', `${esc(item.before?.snapshot_no || '—')} · ${fmtInt(item.rows_before)} 行 · ${fmtBytes(item.before?.bytes)}`],
      ['合并后', `${esc(item.after?.snapshot_no || '—')} · ${fmtInt(item.rows_after)} 行 · ${fmtBytes(item.after?.bytes)}`],
      ['行数守恒', detail.rows_conserved === undefined ? '—' : detail.rows_conserved ? '<span class="badge ok">一致</span>' : '<span class="badge danger">不一致</span>'],
      [
        '校验和',
        `<span class="mono">${esc(detail.checksum_before ?? item.checksum_before)} → ${esc(detail.checksum_after ?? item.checksum_after)}</span>`,
      ],
      ['文件增减', detail.counts ? `新增 ${detail.counts.added} · 移除 ${detail.counts.removed} · 重写 ${detail.counts.rewritten} · 未变 ${detail.counts.unchanged}` : '—'],
      ['提交时间', fmtTime(item.committed_at)],
    ])}
    ${
      (detail.lossy_partitions || []).length
        ? `<h3 style="margin:16px 0 8px;font-size:0.95rem">行数不守恒的分区</h3>
           <div class="rows">${detail.lossy_partitions
             .slice(0, 6)
             .map(
               (row) => `<div class="row-line">
                 <span class="mono">${esc(row.partition_key)}</span>
                 <span class="num">${fmtInt(row.rows_before)}</span>
                 <span class="num">${fmtInt(row.rows_after)}</span>
                 <span class="num" style="color:var(--danger)">${esc(row.rows_delta)}</span>
               </div>`,
             )
             .join('')}</div>
           <p class="muted" style="margin:6px 0 0">列：合并前行数 / 合并后行数 / 差值</p>`
        : ''
    }
    ${
      rewritten.length
        ? `<h3 style="margin:16px 0 8px;font-size:0.95rem">重写分组（前 8 个）</h3>
           <div class="rows">${rewritten
             .map(
               (row) => `<div class="row-line">
                 <span class="mono">${esc(row.partition_key)}</span>
                 <span class="num">${esc(row.files_in)}→${esc(row.files_out)}</span>
                 <span class="num">${fmtInt(row.rows_in)}</span>
                 <span class="num">${fmtInt(row.rows_out)}</span>
               </div>`,
             )
             .join('')}</div>`
        : ''
    }
    <h3 style="margin:16px 0 8px;font-size:0.95rem">校验明细（算法 B 输出）</h3>
    <pre class="code">${esc(
      JSON.stringify(
        {
          verdict: detail.verdict,
          reasons: detail.reasons,
          rows_before: detail.rows_before,
          rows_after: detail.rows_after,
          rows_delta: detail.rows_delta,
          checksum_before: detail.checksum_before,
          checksum_after: detail.checksum_after,
          counts: detail.counts,
        },
        null,
        2,
      ),
    )}</pre>`;

  drawer({
    title: `快照校验 · ${item.table_code} #${item.seq_no}`,
    subtitle: can(ctx.user.role, 'snapshot:verify') ? '已重新调用算法 B 复算' : '只读角色显示服务端已存结论',
    wide: true,
    body,
  });
}

function verifyTab(view, ctx, data) {
  return `
    <section class="panel">
      <div class="panel-head">
        <h2>快照守恒</h2>
        <span class="meta">${fmtInt(data.total)} 组 before/after · 点击行复算</span>
      </div>
      <div class="panel-body">
        <div class="filter-bar" id="snapshot-filters">
          ${field({
            label: '结论',
            name: 'verdict',
            value: state.verdict,
            options: [{ value: '', label: '全部' }, ...Object.entries(ENUMS.verdict).map(([value, label]) => ({ value, label }))],
          })}
          <div class="spacer"></div>
        </div>
      </div>
      ${table({
        rows: data.items,
        empty: { title: '还没有快照', hint: '执行一份合并计划会自动落 before/after 快照。' },
        columns: [
          {
            key: 'table_code',
            label: '湖表',
            render: (row) => `<b class="mono">${esc(row.table_code)}</b><div class="muted">${esc(row.table_name)}</div>`,
          },
          { key: 'seq_no', label: '序号', className: 'num' },
          {
            key: 'rows',
            label: '行数 前→后',
            className: 'num',
            render: (row) => `${fmtInt(row.rows_before)}→${fmtInt(row.rows_after)}`,
          },
          {
            key: 'rows_delta',
            label: '行数差',
            className: 'num',
            render: (row) =>
              row.rows_delta === 0
                ? '<span class="muted">0</span>'
                : `<span style="color:var(--danger)">${esc(row.rows_delta)}</span>`,
          },
          {
            key: 'checksum',
            label: '校验和 前→后',
            className: 'mono',
            render: (row) => `${esc(row.checksum_before)} → ${esc(row.checksum_after)}`,
          },
          {
            key: 'verdict',
            label: '结论',
            render: (row) =>
              row.verdict
                ? `<span class="badge ${esc(verdictTone(row.verdict))}">${esc(ENUMS.verdict[row.verdict] || row.verdict)}</span>`
                : '<span class="muted">未校验</span>',
          },
          { key: 'reasons', label: '原因', className: 'mono', render: (row) => esc((row.reasons || []).join(', ') || '—') },
          { key: 'committed_at', label: '提交时间', render: (row) => fmtTime(row.committed_at) },
        ],
      })}
    </section>`;
}

function exportTab(ctx) {
  const allowed = can(ctx.user.role, 'export:read');
  return `<section class="panel">
    <div class="panel-head"><h2>报表导出</h2><span class="meta">CSV · UTF-8 BOM</span></div>
    <div class="panel-body stack">
      ${
        allowed
          ? notice({ tone: 'ok', title: '可导出', body: '导出会写一条审计记录（export.plans / export.snapshots）。' })
          : notice({ tone: 'warn', title: '当前角色不可导出', body: '导出接口对 analyst / viewer 返回真实 403，只有管理员能下载。' })
      }
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <button class="btn accent" id="export-plans" ${allowed ? '' : 'disabled'}>导出合并计划 CSV</button>
        <button class="btn ghost" id="export-snapshots" ${allowed ? '' : 'disabled'}>导出快照校验 CSV</button>
      </div>
      <div class="rows">
        <div class="row-line"><span>合并计划清单</span><span class="num">计划号 / 合并组 / 节省比例</span><span class="num">冲突</span><span class="num">复核</span></div>
        <div class="row-line"><span>快照校验清单</span><span class="num">行数 / 校验和</span><span class="num">结论</span><span class="num">原因</span></div>
      </div>
    </div>
  </section>`;
}

function auditTab(ctx, audit) {
  if (!can(ctx.user.role, 'audit:read')) {
    return `<section class="panel"><div class="panel-body">${notice({
      tone: 'warn',
      title: '审计只对管理员开放',
      body: 'analyst 调 /api/audit 会拿到真实 403，这里也不做前端伪隐藏之外的任何请求。',
    })}</div></section>`;
  }
  if (!audit) return '<section class="panel"><div class="panel-body"><div class="empty"><div class="mark">读取审计…</div></div></div></section>';
  return `<section class="panel">
    <div class="panel-head"><h2>审计日志</h2><span class="meta">${fmtInt(audit.total)} 条</span></div>
    ${table({
      rows: audit.items,
      empty: { title: '还没有审计记录', hint: '登录、扫描、建计划、执行、导出都会留痕。' },
      columns: [
        { key: 'created_at', label: '时间', render: (row) => fmtTime(row.created_at) },
        { key: 'actor_email', label: '操作人', className: 'mono' },
        { key: 'actor_role', label: '角色' },
        { key: 'action_label', label: '动作' },
        { key: 'entity', label: '对象' },
        { key: 'layer', label: '层', render: (row) => `<span class="badge">${esc(row.layer)}</span>` },
        { key: 'detail', label: '详情', render: (row) => `<span class="mono muted">${esc(JSON.stringify(row.detail || {}))}</span>` },
      ],
    })}
  </section>`;
}

export const snapshotsPage = {
  async render(view, ctx) {
    let pairs;
    try {
      pairs = await api.get('/api/snapshots', { table_id: state.tableId, verdict: state.verdict, limit: 30 });
      if (state.tab === 'audit' && can(ctx.user.role, 'audit:read') && !state.audit) {
        state.audit = await api.get('/api/audit', { limit: 60 });
      }
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => snapshotsPage.render(view, ctx));
      return;
    }
    const tabBody =
      state.tab === 'export' ? exportTab(ctx) : state.tab === 'audit' ? auditTab(ctx, state.audit) : verifyTab(view, ctx, pairs);

    view.innerHTML = `
      <section class="panel">
        <div class="panel-head">
          <h2>快照校验与导出</h2>
          <span class="meta">算法 B：manifest diff + 行数/校验和守恒</span>
        </div>
        ${tabs({
          items: [
            { key: 'verify', label: '快照校验' },
            { key: 'export', label: '导出' },
            { key: 'audit', label: '审计' },
          ],
          active: state.tab,
        })}
        <div class="tab-body">${tabBody}</div>
      </section>`;

    view.querySelectorAll('.tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        state.tab = tab.dataset.tab;
        snapshotsPage.render(view, ctx);
      });
    });

    if (state.tab === 'verify') {
      const filters = view.querySelector('#snapshot-filters');
      filters?.addEventListener('change', () => {
        state.verdict = filters.querySelector('[name=verdict]').value;
        snapshotsPage.render(view, ctx);
      });
      view.querySelectorAll('table.data tbody tr').forEach((row) => {
        row.addEventListener('click', () => {
          const item = pairs.items.find((entry) => entry.key === String(row.dataset.id));
          if (item) openPair(view, ctx, item);
        });
      });
    }

    view.querySelector('#export-plans')?.addEventListener('click', async () => {
      try {
        await api.download('/api/exports/plans.csv', 'compaction-plans.csv');
        toast('已开始下载合并计划 CSV');
      } catch (err) {
        toast(errorMessage(err), 'err');
      }
    });
    view.querySelector('#export-snapshots')?.addEventListener('click', async () => {
      try {
        await api.download('/api/exports/snapshots.csv', 'snapshot-verify.csv');
        toast('已开始下载快照校验 CSV');
      } catch (err) {
        toast(errorMessage(err), 'err');
      }
    });
  },
};

export default snapshotsPage;
