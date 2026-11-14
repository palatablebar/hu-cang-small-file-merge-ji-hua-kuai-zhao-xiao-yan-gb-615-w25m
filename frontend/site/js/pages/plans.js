import { api } from '../api.js';
import { ENUMS, can, reviewTone, statusTone, verdictTone } from '../config.js';
import {
  chips,
  drawer,
  emptyState,
  errorBox,
  errorMessage,
  esc,
  field,
  fmtBytes,
  fmtInt,
  fmtPct,
  fmtTime,
  kv,
  meter,
  notice,
  table,
  toast,
} from '../ui.js';

const state = { tableId: '', status: '', reviewStatus: '' };

function groupCards(groups) {
  if (!groups.length) return emptyState({ title: '这份计划没有合并分组', hint: '分区文件数不足或全部是大文件。' });
  return `<div class="group-grid">${groups
    .slice(0, 12)
    .map(
      (group) => `<div class="group-card">
        <span class="no">#${esc(String(group.group_no).padStart(2, '0'))}</span>
        <span>
          <b class="mono" style="font-size:0.78rem">${esc(group.partition_key)}</b>
          <div class="paths">${esc((group.paths || []).slice(0, 2).join('  ·  '))}${(group.paths || []).length > 2 ? ` …+${group.paths.length - 2}` : ''}</div>
        </span>
        <span class="meta">${esc(group.files)} 文件<br />${fmtBytes(group.bytes)}<br />${fmtInt(group.rows)} 行</span>
      </div>`,
    )
    .join('')}</div>
    ${groups.length > 12 ? `<p class="muted" style="margin:8px 0 0">仅显示前 12 组，共 ${groups.length} 组；完整清单见 CSV 导出。</p>` : ''}`;
}

async function execute(view, ctx, item, root, close) {
  try {
    const result = await api.post(`/api/compaction-jobs/${item.id}/execute`);
    toast(`已执行 ${result.plan_no}：快照 ${ENUMS.verdict[result.verdict] || result.verdict}`);
    close();
    await plansPage.render(view, ctx);
  } catch (err) {
    const reason = err.detail?.reason;
    const text =
      reason === 'snapshot_lossy'
        ? '快照守恒校验未通过（lossy），已阻止执行；先补跑上游或重做合并。'
        : reason === 'stream_conflict'
          ? '合并窗口与流读窗口相交，已阻止执行；请先重排窗口。'
          : reason === 'already_executed'
            ? '这份计划已经执行过了。'
            : errorMessage(err);
    root.querySelector('#plan-error').textContent = text;
    toast(text, 'err');
  }
}

function openPlan(view, ctx, item) {
  const canExecute = can(ctx.user.role, 'plan:execute');
  const canReview = can(ctx.user.role, 'plan:review');
  const canReschedule = can(ctx.user.role, 'plan:create');
  const metrics = item.metrics || {};
  const conflict = item.conflict || {};
  const suggestion = conflict.suggested_window || {};
  const verify = item.verify || {};
  const verifyBody = verify.verdict
    ? notice({
        tone: verify.verdict === 'consistent' ? 'ok' : verify.verdict === 'lossy' ? 'danger' : 'warn',
        title: `快照结论：${ENUMS.verdict[verify.verdict] || verify.verdict}`,
        body: `原因 ${esc((verify.reasons || []).join(', ') || '—')}${
          verify.rows_delta !== undefined ? ` · 行数差 ${esc(verify.rows_delta)}` : ''
        }${verify.blocked_by ? ` · 阻断点 ${esc(verify.blocked_by)}` : ''}`,
      })
    : notice({ tone: 'warn', title: '尚未校验', body: '执行时会先落 before/after 快照并做守恒校验。' });

  const body = `
    ${conflict.conflict
      ? notice({
          tone: 'danger',
          title: `撞上流读窗口（重叠 ${fmtInt(conflict.overlap_minutes)} 分钟）`,
          body: `流读窗口 ${esc(conflict.stream_window?.start)}–${esc(conflict.stream_window?.end)}；
            建议改到 <b class="mono">${esc(suggestion.start)} → ${esc(suggestion.end)}</b>（${esc(conflict.suggestion_note || '')}）`,
        })
      : notice({ tone: 'ok', title: '窗口安全', body: '合并窗口与流读窗口无交集，可执行。' })}
    ${verifyBody}
    ${kv([
      ['计划号', `<span class="mono">${esc(item.plan_no)}</span>`],
      ['湖表', `${esc(item.table_code)} · ${esc(item.table_name)}`],
      ['窗口', `<span class="mono">${fmtTime(item.window_start)} → ${fmtTime(item.window_end)}</span>`],
      ['目标 / 最小文件数', `${esc(item.target_mb)} MB · ${esc(item.min_files)} 个`],
      ['触发方式', esc(item.trigger_label)],
      ['合并前文件', fmtInt(metrics.files_before)],
      ['合并后文件', fmtInt(metrics.expected_files_after)],
      ['IO 节省比例', `${fmtPct(metrics.io_saved_ratio)} ${meter(metrics.io_saved_ratio)}`],
      ['平均装箱填充', fmtPct(metrics.avg_fill_ratio)],
      ['合并前字节', fmtBytes(metrics.bytes_before)],
      ['FFD / 理论下界', `${fmtInt(metrics.groups_total)} / ${fmtInt(metrics.bins_lower_bound)} 桶`],
      ['复核', `<span class="badge ${reviewTone(item.review_status)}">${esc(item.review_status_label)}</span> ${
        item.reviewer ? esc(item.reviewer) : ''
      } ${item.review_note ? `· ${esc(item.review_note)}` : ''}`],
    ])}
    <h3 style="margin:16px 0 8px;font-size:0.95rem">合并分组（${fmtInt(item.merge_group_count)} 组）</h3>
    ${groupCards(item.merge_groups || [])}
    ${
      (item.rewrite_partitions || []).length
        ? `<h3 style="margin:16px 0 8px;font-size:0.95rem">需先 rewrite 的分区</h3>
           ${chips(item.rewrite_partitions.map((row) => ({ text: `${row.partition_key} · delete ${row.delete_files}`, tone: 'danger' })))}`
        : ''
    }
    ${
      (item.skipped_partitions || []).length
        ? `<h3 style="margin:16px 0 8px;font-size:0.95rem">跳过的分区</h3>
           ${chips(item.skipped_partitions.map((row) => ({ text: `${row.partition_key} · ${row.reason}`, tone: 'warn' })))}`
        : ''
    }
    <div id="plan-error" class="form-error" style="margin-top:12px"></div>`;

  const footer = `<div style="display:grid;gap:10px;width:100%">
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      ${canExecute ? `<button class="btn accent" data-execute ${item.status === 'executed' ? 'disabled' : ''}>执行合并</button>` : ''}
      ${canReschedule ? '<button class="btn ghost" data-reschedule>重排窗口</button>' : ''}
      <span class="mono muted" style="align-self:center">${
        canExecute ? '执行会先做快照守恒校验' : '当前角色只能预览，不能执行'
      }</span>
    </div>
    ${
      canReview
        ? `<form id="review-form" style="display:grid;gap:8px;border-top:1px dashed var(--rule);padding-top:10px">
            <div class="inline-fields">
              ${field({ label: '复核结论', name: 'status', value: item.review_status, options: Object.entries(ENUMS.review).map(([value, label]) => ({ value, label })) })}
              ${field({ label: '备注', name: 'note', value: item.review_note || '', placeholder: '写一句判定依据' })}
            </div>
            <button class="btn ghost" type="submit">提交复核</button>
          </form>`
        : '<span class="mono muted">只读角色不可复核</span>'
    }
  </div>`;

  const { root, close } = drawer({
    title: `合并计划 ${item.plan_no}`,
    subtitle: `${item.table_code} · ${item.status_label}`,
    wide: true,
    body,
    footer,
  });

  root.querySelector('[data-execute]')?.addEventListener('click', () => execute(view, ctx, item, root, close));
  root.querySelector('[data-reschedule]')?.addEventListener('click', () => openReschedule(view, ctx, item, close));
  root.querySelector('#review-form')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.target;
    try {
      await api.patch(`/api/compaction-jobs/${item.id}/review`, {
        status: form.status.value,
        note: form.note.value.trim() || null,
      });
      toast('复核结论已保存');
      close();
      await plansPage.render(view, ctx);
    } catch (err) {
      toast(errorMessage(err), 'err');
    }
  });
}

function openReschedule(view, ctx, item, parentClose) {
  const start = (item.window_start || '').slice(0, 16);
  const end = (item.window_end || '').slice(0, 16);
  const { root, close } = drawer({
    title: '重排合并窗口',
    subtitle: `${item.plan_no} · 当前建议 ${(item.conflict?.suggested_window || {}).start || '—'}`,
    body: `<form id="window-form" style="display:grid;gap:12px">
      ${field({ label: '窗口开始', name: 'window_start', type: 'datetime-local', value: start })}
      ${field({ label: '窗口结束', name: 'window_end', type: 'datetime-local', value: end })}
      <p class="muted" style="margin:0">流读保护区间为 [开始 − 流读延迟, 结束]，与流读窗口相交会被判定冲突。</p>
      <div class="form-error" id="window-error"></div>
      <button class="btn accent" type="submit">保存窗口</button>
    </form>`,
  });
  root.querySelector('#window-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.target;
    try {
      await api.patch(`/api/compaction-jobs/${item.id}/window`, {
        window_start: form.window_start.value,
        window_end: form.window_end.value,
      });
      toast('窗口已更新');
      close();
      parentClose?.();
      await plansPage.render(view, ctx);
    } catch (err) {
      root.querySelector('#window-error').textContent = errorMessage(err);
    }
  });
}

function openCreate(view, ctx, tables) {
  const now = new Date();
  const pad = (value) => String(value).padStart(2, '0');
  const start = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T07:30`;
  const end = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T08:30`;
  const { root, close } = drawer({
    title: '生成合并计划',
    subtitle: '算法在后端执行：FFD 装箱 + delete 分区 rewrite 标记 + 流读冲突窗口',
    body: `<form id="plan-form" style="display:grid;gap:12px">
      ${field({
        label: '湖表',
        name: 'table_id',
        options: tables.map((item) => ({ value: item.id, label: `${item.code} · ${item.name}` })),
      })}
      <div class="inline-fields">
        ${field({ label: '目标文件 MB', name: 'target_mb', type: 'number', value: '128', attrs: 'min="1" max="1024"' })}
        ${field({ label: '最小文件数', name: 'min_files', type: 'number', value: '5', attrs: 'min="2" max="100"' })}
        ${field({ label: '流读延迟（秒）', name: 'flow_lag_seconds', type: 'number', value: '900', attrs: 'min="0" max="7200"' })}
      </div>
      <div class="inline-fields">
        ${field({ label: '窗口开始', name: 'window_start', type: 'datetime-local', value: start })}
        ${field({ label: '窗口结束', name: 'window_end', type: 'datetime-local', value: end })}
      </div>
      ${field({
        label: '触发方式',
        name: 'trigger',
        value: 'manual',
        options: Object.entries(ENUMS.trigger).map(([value, label]) => ({ value, label })),
      })}
      <div class="form-error" id="plan-error"></div>
      <button class="btn accent" type="submit">生成计划</button>
    </form>`,
  });
  root.querySelector('#plan-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.target;
    const button = form.querySelector('button[type=submit]');
    button.disabled = true;
    button.textContent = '装箱中…';
    try {
      const job = await api.post('/api/compaction-jobs', {
        table_id: Number(form.table_id.value),
        target_bytes: Math.round(Number(form.target_mb.value) * 1024 * 1024),
        min_files: Number(form.min_files.value),
        flow_lag_seconds: Number(form.flow_lag_seconds.value),
        window_start: form.window_start.value,
        window_end: form.window_end.value,
        trigger: form.trigger.value,
      });
      toast(
        `计划 ${job.plan_no} 已生成：${job.merge_group_count} 组，文件 ${job.metrics.files_before} → ${job.metrics.expected_files_after}`,
      );
      close();
      await plansPage.render(view, ctx);
    } catch (err) {
      root.querySelector('#plan-error').textContent =
        err.code === 'VALIDATION' ? '参数不合法：目标大小 / 最小文件数 / 窗口时间' : errorMessage(err);
      button.disabled = false;
      button.textContent = '生成计划';
    }
  });
}

export const plansPage = {
  async render(view, ctx) {
    let tables;
    let jobs;
    try {
      [tables, jobs] = await Promise.all([
        api.get('/api/tables', { limit: 50 }),
        api.get('/api/compaction-jobs', {
          table_id: state.tableId,
          status: state.status,
          review_status: state.reviewStatus,
          limit: 40,
        }),
      ]);
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => plansPage.render(view, ctx));
      return;
    }
    view.innerHTML = `
      <section class="panel">
        <div class="panel-head">
          <h2>合并计划</h2>
          <div style="display:flex;gap:8px;align-items:center">
            <span class="meta">${fmtInt(jobs.total)} 份计划</span>
            ${can(ctx.user.role, 'plan:create') ? '<button class="btn sm accent" id="new-plan">生成计划</button>' : ''}
          </div>
        </div>
        <div class="panel-body">
          <div class="filter-bar" id="plan-filters">
            ${field({
              label: '湖表',
              name: 'table_id',
              value: state.tableId,
              options: [{ value: '', label: '全部' }, ...tables.items.map((item) => ({ value: item.id, label: item.code }))],
            })}
            ${field({
              label: '状态',
              name: 'status',
              value: state.status,
              options: [{ value: '', label: '全部' }, ...Object.entries(ENUMS.jobStatus).map(([value, label]) => ({ value, label }))],
            })}
            ${field({
              label: '复核',
              name: 'review_status',
              value: state.reviewStatus,
              options: [{ value: '', label: '全部' }, ...Object.entries(ENUMS.review).map(([value, label]) => ({ value, label }))],
            })}
            <div class="spacer"></div>
          </div>
        </div>
        ${table({
          rows: jobs.items,
          empty: { title: '还没有合并计划', hint: '管理员选一张湖表点「生成计划」。' },
          columns: [
            { key: 'plan_no', label: '计划号', className: 'mono' },
            {
              key: 'table_code',
              label: '湖表',
              render: (row) => `<b class="mono">${esc(row.table_code)}</b><div class="muted">${esc(row.layer || '')}</div>`,
            },
            { key: 'merge_group_count', label: '合并组', className: 'num' },
            {
              key: 'metrics',
              label: '文件 前→后',
              className: 'num',
              render: (row) => `${fmtInt(row.metrics?.files_before)}→${fmtInt(row.metrics?.expected_files_after)}`,
            },
            {
              key: 'io_saved_ratio',
              label: '节省比例',
              className: 'num',
              render: (row) => `<b>${fmtPct(row.metrics?.io_saved_ratio)}</b>`,
            },
            {
              key: 'conflict',
              label: '冲突',
              render: (row) =>
                row.conflict?.conflict
                  ? `<span class="badge danger">重叠 ${fmtInt(row.conflict.overlap_minutes)} 分</span>`
                  : '<span class="badge ok">安全</span>',
            },
            {
              key: 'status',
              label: '状态',
              render: (row) => `<span class="badge ${esc(statusTone(row.status))}">${esc(row.status_label)}</span>`,
            },
            {
              key: 'verdict',
              label: '快照',
              render: (row) =>
                row.verdict
                  ? `<span class="badge ${esc(verdictTone(row.verdict))}">${esc(ENUMS.verdict[row.verdict] || row.verdict)}</span>`
                  : '<span class="muted">未校验</span>',
            },
            {
              key: 'review_status',
              label: '复核',
              render: (row) => `<span class="badge ${esc(reviewTone(row.review_status))}">${esc(row.review_status_label)}</span>`,
            },
          ],
        })}
      </section>`;

    const filters = view.querySelector('#plan-filters');
    filters?.addEventListener('change', () => {
      state.tableId = filters.querySelector('[name=table_id]').value;
      state.status = filters.querySelector('[name=status]').value;
      state.reviewStatus = filters.querySelector('[name=review_status]').value;
      plansPage.render(view, ctx);
    });
    view.querySelectorAll('table.data tbody tr').forEach((row) => {
      row.addEventListener('click', () => {
        const item = jobs.items.find((entry) => String(entry.id) === row.dataset.id);
        if (item) openPlan(view, ctx, item);
      });
    });
    view.querySelector('#new-plan')?.addEventListener('click', () => openCreate(view, ctx, tables.items));
  },
};

export default plansPage;
