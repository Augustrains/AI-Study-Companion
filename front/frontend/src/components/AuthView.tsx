import { useState, type FormEvent } from "react";
import { Icon } from "./Icon";
import { auth, type AuthSession } from "../services/session";

type Mode = "login" | "register";
type LoginMethod = "password" | "code";

const errorMessage = (error: unknown) =>
  (error as { message?: string })?.message ?? "操作失败，请稍后重试。";

/** 与注册页展示的强度条对应的简单规则，仅用于即时反馈。 */
function passwordStrength(password: string): { level: number; label: string } {
  if (!password) return { level: 0, label: "请输入密码" };
  let level = 0;
  if (password.length >= 8) level += 1;
  if (/[a-zA-Z]/.test(password) && /\d/.test(password)) level += 1;
  if (password.length >= 12) level += 1;
  if (/[^a-zA-Z0-9]/.test(password)) level += 1;
  return { level, label: ["太短", "偏弱", "一般", "良好", "很强"][level] };
}

export function AuthView({ onAuthenticated }: { onAuthenticated: (session: AuthSession) => void }) {
  const [mode, setMode] = useState<Mode>("login");
  const [loginMethod, setLoginMethod] = useState<LoginMethod>("password");

  const [account, setAccount] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [nickname, setNickname] = useState("");
  const [code, setCode] = useState("");
  const [agreed, setAgreed] = useState(true);
  const [remember, setRemember] = useState(true);
  const [showPassword, setShowPassword] = useState(false);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [codeCooldown, setCodeCooldown] = useState(0);

  const strength = passwordStrength(password);

  const switchMode = (next: Mode) => {
    setMode(next);
    setError(null);
    setNotice(null);
    setPassword("");
    setConfirmPassword("");
    setCode("");
  };

  const startCooldown = () => {
    setCodeCooldown(60);
    const timer = window.setInterval(() => {
      setCodeCooldown((value) => {
        if (value <= 1) {
          window.clearInterval(timer);
          return 0;
        }
        return value - 1;
      });
    }, 1000);
  };

  const sendCode = async () => {
    if (!account.trim()) {
      setError("请先填写邮箱或手机号。");
      return;
    }
    setError(null);
    try {
      const result = await auth.sendLoginCode(account.trim());
      startCooldown();
      if (result.fallback) {
        setNotice("后端验证码接口尚未接入，本地联调请输入任意 4 位以上字符。");
      } else if (result.devCode) {
        // 后端开发模式：验证码直接显示在页面上，不走真实邮件/短信通道。
        setNotice(`开发模式验证码：${result.devCode}（上线后将改为发送到邮箱 / 手机）`);
        setCode(result.devCode);
      } else {
        setNotice("验证码已发送，请查收。");
      }
    } catch (sendError) {
      setError(errorMessage(sendError));
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setNotice(null);

    if (!account.trim()) return setError("请填写邮箱或手机号。");

    if (mode === "register") {
      if (!nickname.trim()) return setError("请填写昵称。");
      if (password.length < 8) return setError("密码至少需要 8 位。");
      if (password !== confirmPassword) return setError("两次输入的密码不一致。");
      if (!agreed) return setError("请先阅读并同意用户协议与隐私政策。");
    } else if (loginMethod === "password") {
      if (!password) return setError("请填写密码。");
    } else if (!code.trim()) {
      return setError("请填写验证码。");
    }

    setBusy(true);
    try {
      const session =
        mode === "register"
          ? await auth.register({ nickname: nickname.trim(), account: account.trim(), password })
          : loginMethod === "password"
            ? await auth.login({ account: account.trim(), password })
            : await auth.loginByCode({ account: account.trim(), code: code.trim() });
      onAuthenticated(session);
    } catch (submitError) {
      setError(errorMessage(submitError));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-canvas">
      <div className="auth-wrap">
        <div className="auth-brand">
          <div className="brand-mark"><Icon name="book-open" size={24} /></div>
          <b>自适应伴学智能体</b>
          <span>Adaptive Learning</span>
        </div>

        <form className="card auth-card" onSubmit={submit}>
          <h1>{mode === "login" ? "欢迎回来" : "创建账号"}</h1>
          <p className="auth-sub">
            {mode === "login" ? "登录后继续你的学习计划与复习安排。" : "几步就能开始你的第一次能力诊断。"}
          </p>

          {mode === "register" && (
            <label className="auth-field">
              <span>昵称</span>
              <input value={nickname} onChange={(event) => setNickname(event.target.value)} placeholder="怎么称呼你" autoComplete="nickname" />
            </label>
          )}

          <label className="auth-field">
            <span>邮箱或手机号</span>
            <input value={account} onChange={(event) => setAccount(event.target.value)} placeholder="you@example.com" autoComplete="username" />
          </label>

          {mode === "login" && loginMethod === "code" ? (
            <label className="auth-field">
              <span>验证码</span>
              <div className="auth-input-wrap">
                <input value={code} onChange={(event) => setCode(event.target.value)} placeholder="6 位验证码" inputMode="numeric" autoComplete="one-time-code" />
                <button type="button" className="auth-inline-action" onClick={sendCode} disabled={codeCooldown > 0}>
                  {codeCooldown > 0 ? `${codeCooldown}s 后重发` : "获取验证码"}
                </button>
              </div>
            </label>
          ) : (
            <label className="auth-field">
              <span>密码</span>
              <div className="auth-input-wrap">
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder={mode === "register" ? "至少 8 位，包含字母和数字" : "输入密码"}
                  autoComplete={mode === "register" ? "new-password" : "current-password"}
                />
                <button type="button" className="auth-inline-action" onClick={() => setShowPassword((value) => !value)}>
                  {showPassword ? "隐藏" : "显示"}
                </button>
              </div>
              {mode === "register" && (
                <>
                  <div className="pw-meter">
                    {[0, 1, 2, 3].map((index) => <i key={index} className={index < strength.level ? "on" : ""} />)}
                  </div>
                  <div className="pw-hint">强度：{strength.label}</div>
                </>
              )}
            </label>
          )}

          {mode === "register" && (
            <label className="auth-field">
              <span>确认密码</span>
              <input type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} placeholder="再次输入密码" autoComplete="new-password" />
            </label>
          )}

          {mode === "login" ? (
            <div className="auth-field-row">
              <label className="auth-remember">
                <input type="checkbox" checked={remember} onChange={(event) => setRemember(event.target.checked)} />
                记住我
              </label>
              <button
                type="button"
                className="auth-link"
                onClick={() => setLoginMethod((method) => (method === "password" ? "code" : "password"))}
              >
                {loginMethod === "password" ? "使用验证码登录" : "使用密码登录"}
              </button>
            </div>
          ) : (
            <label className="auth-terms">
              <input type="checkbox" checked={agreed} onChange={(event) => setAgreed(event.target.checked)} />
              <span>我已阅读并同意《用户协议》与《隐私政策》，理解学习数据将用于生成个性化的掌握度评估与复习计划。</span>
            </label>
          )}

          {error && <div className="auth-message error"><Icon name="alert" size={15} /><span>{error}</span></div>}
          {notice && <div className="auth-message notice"><Icon name="info" size={15} /><span>{notice}</span></div>}

          <button className="auth-submit" type="submit" disabled={busy}>
            {busy ? "处理中…" : mode === "login" ? "登录" : "创建账号"}
          </button>

          <div className="auth-foot">
            {mode === "login" ? (
              <>还没有账号？<button type="button" className="auth-link" onClick={() => switchMode("register")}>立即注册</button></>
            ) : (
              <>已有账号？<button type="button" className="auth-link" onClick={() => switchMode("login")}>去登录</button></>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
