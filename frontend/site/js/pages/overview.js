import { api } from '../api.js';
import { ENUMS, statusTone, verdictTone } from '../config.js';
import { barList, emptyState, errorBox, errorMessage, esc, fmtBytes, fmtInt, fmtPct, fmtTime, meter, table } from '../ui.js';

function hero(data) {
  const gain = data.latest_gain;
  return `<div class="hero">
    <div class="hero-main">
      <h2>小文件体检台</h2>
      <p class="hint">小文件阈值 ${fmtBytes(data.small_file_threshold)}；删改分区必须先 rewrite 再合并。</p>
      <div class="hero-stats">
        <div class="hero-stat"><span class="k">湖表</span><span class="v">${fmtInt(data.tables_total)}</span><span class="u">${fmtInt(data.partitions_total)} 个分区</span></div>
        <div class="hero-stat"><span class="k">manifest 文件</span><span class="v">${fmtInt(data.files_total)}</span><span class="u">${fmtInt(data.rows_total)} 行</span></div>
        <div class="hero-stat"><span class="k">小文件</span><span class="v">${fmtInt(data.small_files)}</span><span class="u">占比 ${fmtPct(data.small_file_ratio)}</span></div>
        <div class="hero-stat"><span class="k">待 rewrite 分区</span><span class="v">${fmtInt(data.rewrite_partitions)}</span><span class="u">${fmtInt(data.delete_files)} 个 delete 文件</span></div>
      </div>
    </div>
    <div class="hero-gain">
      <span class="cap">最近一次执行收益（io_saved_ratio）</span>
      <span class="ratio" data-testid="gain-ratio">${gain ? fmtPct(gain.io_saved_ratio) : '—'}</span>
      ${meter(gain ? gain.io_saved_ratio : 0)}
      <span class="cap">${
        gain
          ? `${esc(gain.plan_no)} · 文件 ${fmtInt(gain.files_before)} → ${fmtInt(gain.expected_files_after)}`
          : '暂无执行记录'
      }</span>
      <span class="cap">${
        gain
          ? `回收字节 ${fmtBytes(gain.bytes_before)} · 平均装箱 ${fmtPct(gain.avg_fill_ratio)}`
          : '建计划并执行后这里显示收益'
      }</span>
    </div>
  </div>`;
}

export const overviewPage = {
  async render(view, ctx) {
    view.innerHTML = '<div class="empty"><div class="mark">读取总览…</div></div>';
    try {
      const data = await api.get('/api/overview');
      view.innerHTML = `
        ${hero(data)}
        <div class="grid-3">
          <section class="panel">
            <div class="panel-head"><h2>小文件集中度</h2><span class="meta">top 6</span></div>
            <div class="panel-body">
              ${
                data.top_tables.length
                  ? `<div class="rows">${data.top_tables
                      .map(
                        (item) => `<div class="row-line" data-testid="top-${esc(item.table_code)}">
                          <span><b>${esc(item.table_code)}</b><br /><span class="mono muted">${esc(item.table_name)}</span></span>
                          <span class="num">${fmtInt(item.small_files)}</span>
                          <span class="num">${fmtInt(item.files)}</span>
                          <span class="num">${fmtPct(item.small_ratio)}</span>
                        </div>`,
                      )
                      .join('')}</div>
                    <p class="muted" style="margin:8px 0 0">列：小文件 / 文件总数 / 小文件占比</p>`
                  : emptyState({ title: '还没有文件', hint: '先在「表与分区」登记湖表并扫描 manifest。' })
              }
            </div>
          </section>
          <section class="panel">
            <div class="panel-head"><h2>分层分布</h2><span class="meta">files / layer</span></div>
            <div class="panel-body">${barList(data.layer_distribution.map((item) => ({ label: item.label, count: item.files })))}</div>
          </section>
          <section class="panel">
            <div class="panel-head"><h2>快照守恒</h2><span class="meta">verdict</span></div>
            <div class="panel-body">${barList(
              data.verdicts.map((item) => ({ label: item.label, count: item.count })),
              'ok',
            )}</div>
          </section>
        </div>
        <div class="grid-2">
          <section class="panel">
            <div class="panel-head">
              <h2>最近合并计划</h2>
              <span class="meta">${fmtInt(data.plans.total)} 个 · 待复核 ${fmtInt(data.plans.pending_review)}</span>
            </div>
            ${table({
              rows: data.recent_jobs,
              columns: [
                { key: 'plan_no', label: '计划', className: 'mono' },
                { key: 'table_code', label: '湖表' },
                {
                  key: 'status',
                  label: '状态',
                  render: (row) =>
                    `<span class="badge ${esc(statusTone(row.status))}">${esc(ENUMS.jobStatus[row.status] || row.status)}</span>`,
                },
                {
                  key: 'metrics',
                  label: '收益',
                  className: 'num',
                  render: (row) => (row.metrics?.io_saved_ratio !== undefined ? fmtPct(row.metrics.io_saved_ratio) : '—'),
                },
                {
                  key: 'verdict',
                  label: '快照',
                  render: (row) =>
                    row.verdict
                      ? `<span class="badge ${esc(verdictTone(row.verdict))}">${esc(ENUMS.verdict[row.verdict] || row.verdict)}</span>`
                      : '<span class="muted">未校验</span>',
                },
              ],
              empty: { title: '还没有合并计划', hint: '管理员可以在「合并计划」里按湖表生成第一份计划。' },
            })}
          </section>
          <section class="panel">
            <div class="panel-head"><h2>计划状态</h2><span class="meta">status</span></div>
            <div class="panel-body">
              <div class="rows">
                <div class="row-line"><span>待执行</span><span class="num">${fmtInt(data.plans.planned)}</span><span class="num">—</span><span class="num">—</span></div>
                <div class="row-line"><span>已执行</span><span class="num">${fmtInt(data.plans.executed)}</span><span class="num">—</span><span class="num">—</span></div>
                <div class="row-line"><span>校验阻断</span><span class="num">${fmtInt(data.plans.blocked)}</span><span class="num">—</span><span class="num">—</span></div>
                <div class="row-line"><span>待复核</span><span class="num">${fmtInt(data.plans.pending_review)}</span><span class="num">—</span><span class="num">—</span></div>
              </div>
              <p class="muted" style="margin:10px 0 0">
                后台任务：${data.worker_alive ? '心跳在岗' : '心跳超时'} ·
                统计时间 ${fmtTime(new Date().toISOString())}
              </p>
            </div>
          </section>
        </div>`;
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => overviewPage.render(view, ctx));
    }
  },
};

export default overviewPage;
