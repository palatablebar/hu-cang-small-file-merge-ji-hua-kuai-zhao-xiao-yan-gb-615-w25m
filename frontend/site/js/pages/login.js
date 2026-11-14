import { api } from '../api.js';
import { session } from '../store.js';
import { BRAND } from '../config.js';
import { errorMessage, toast } from '../ui.js';

export const loginPage = {
  async render(root, ctx) {
    root.className = '';
    root.innerHTML = `
      <div class="gate">
        <section class="gate-main">
          <div class="gate-mark">
            <b>compactlab</b>
            <span>${BRAND.edition}</span>
          </div>
          <div class="gate-lead">
            <h1>合并小文件，<br />还要能<em>证明数据没丢</em>。</h1>
            <p>${BRAND.loginLead}</p>
          </div>
          <div class="gate-ledger">
            ${BRAND.loginSteps
              .map(
                ([no, name, detail]) =>
                  `<div class="ledger-row"><i>${no}</i><b>${name}</b><span>${detail}</span></div>`,
              )
              .join('')}
          </div>
          <div class="gate-foot">
            <span>${BRAND.org}</span>
            <span>内部值班系统</span>
          </div>
        </section>
        <section class="gate-form">
          <form class="gate-card" id="login-form" novalidate>
            <div>
              <div class="brand">${BRAND.title}</div>
              <div class="sub">三个演示账号权限不同：管理员建计划与执行，数据专员扫描与复核，值班只读只能看比例。</div>
              <div class="gate-rule"></div>
            </div>
            <div class="field">
              <label for="email">邮箱</label>
              <input id="email" name="email" type="email" autocomplete="username" value="admin@${BRAND.short}.io" required />
            </div>
            <div class="field">
              <label for="password">密码</label>
              <input id="password" name="password" type="password" autocomplete="current-password" value="Demo@2026" required />
            </div>
            <div class="form-error" id="login-error" role="alert"></div>
            <button class="btn accent" id="login-submit" type="submit">进入工作台</button>
            <div class="login-hint">
              演示账号（密码 <code>Demo@2026</code>）：<br />
              <code>admin@${BRAND.short}.io</code> 管理员 · <code>analyst@${BRAND.short}.io</code> 数据专员 ·
              <code>viewer@${BRAND.short}.io</code> 只读
            </div>
          </form>
        </section>
      </div>`;

    const form = root.querySelector('#login-form');
    const errorNode = root.querySelector('#login-error');
    const submit = root.querySelector('#login-submit');
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      errorNode.textContent = '';
      submit.disabled = true;
      submit.textContent = '正在验证…';
      try {
        const result = await api.post('/api/auth/login', {
          email: form.email.value.trim(),
          password: form.password.value,
        });
        session.set(result.access_token, result.user);
        toast(`欢迎回来，${result.user.display_name}`);
        location.hash = '#/overview';
        await ctx.reload();
      } catch (err) {
        errorNode.textContent = err.code === 'AUTH_INVALID' ? '账号或密码不正确' : errorMessage(err);
      } finally {
        submit.disabled = false;
        submit.textContent = '进入工作台';
      }
    });
  },
};

export default loginPage;
