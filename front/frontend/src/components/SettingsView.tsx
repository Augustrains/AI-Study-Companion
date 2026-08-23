import { useState } from "react";
import { Icon } from "./Icon";
import { auth, isLocalAuthFallback, type AuthUser } from "../services/session";

type SectionKey = "profile" | "notification" | "security" | "privacy";

const SECTIONS: Array<{ key: SectionKey; label: string }> = [
  { key: "profile", label: "个人信息" },
  { key: "notification", label: "通知偏好" },
  { key: "security", label: "账号安全" },
  { key: "privacy", label: "数据与隐私" },
];

/**
 * 通知偏好目前保存在本地。
 * 【后端接入清单】GET/PATCH /api/user-preferences -> { reviewDue, dailyReminder, weeklyDigest }
 * 其中 reviewDue 对应「到期复习主动推入今日学习」的开关。
 */
const PREFERENCE_KEY = "study-companion.preferences";

type Preferences = { reviewDue: boolean; dailyReminder: boolean; weeklyDigest: boolean };

const defaultPreferences: Preferences = { reviewDue: true, dailyReminder: false, weeklyDigest: true };

function readPreferences(): Preferences {
  try {
    const raw = window.localStorage.getItem(PREFERENCE_KEY);
    return raw ? { ...defaultPreferences, ...(JSON.parse(raw) as Partial<Preferences>) } : defaultPreferences;
  } catch {
    return defaultPreferences;
  }
}

const errorMessage = (error: unknown) => (error as { message?: string })?.message ?? "操作失败，请稍后重试。";

export function SettingsView({
  user,
  onUserUpdated,
  onLogout,
}: {
  user: AuthUser;
  onUserUpdated: (user: AuthUser) => void;
  onLogout: () => void;
}) {
  const [section, setSection] = useState<SectionKey>("profile");
  const [nickname, setNickname] = useState(user.nickname);
  const [preferences, setPreferences] = useState<Preferences>(readPreferences);
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [showPasswordForm, setShowPasswordForm] = useState(false);

  const notify = (tone: "success" | "error", text: string) => {
    setMessage({ tone, text });
    window.setTimeout(() => setMessage(null), 3200);
  };

  const savePreferences = (patch: Partial<Preferences>) => {
    const next = { ...preferences, ...patch };
    setPreferences(next);
    try {
      window.localStorage.setItem(PREFERENCE_KEY, JSON.stringify(next));
    } catch {
      // 本地存储不可用时仅保留内存态。
    }
  };

  const saveNickname = async () => {
    if (!nickname.trim()) return notify("error", "昵称不能为空。");
    setBusy(true);
    try {
      const updated = await auth.updateProfile({ nickname: nickname.trim() });
      onUserUpdated(updated);
      notify("success", "昵称已更新。");
    } catch (error) {
      notify("error", errorMessage(error));
    } finally {
      setBusy(false);
    }
  };

  const savePassword = async () => {
    if (newPassword.length < 8) return notify("error", "新密码至少需要 8 位。");
    setBusy(true);
    try {
      await auth.updatePassword({ currentPassword, newPassword });
      setCurrentPassword("");
      setNewPassword("");
      setShowPasswordForm(false);
      notify("success", "密码已修改。");
    } catch (error) {
      notify("error", errorMessage(error));
    } finally {
      setBusy(false);
    }
  };

  const logout = async () => {
    await auth.logout();
    onLogout();
  };

  return (
    <div className="page-stack">
      <div className="page-header">
        <div>
          <span className="eyebrow">Account</span>
          <h1>账户设置</h1>
        </div>
      </div>

      {isLocalAuthFallback() && (
        <div className="auth-message notice" style={{ marginBottom: 16 }}>
          <Icon name="info" size={15} />
          <span>后端认证接口尚未接入，当前使用本地会话。接口上线后前端无需改动即可切换。</span>
        </div>
      )}

      {message && (
        <div className={`auth-message ${message.tone === "success" ? "success" : "error"}`} style={{ marginBottom: 16 }}>
          <Icon name={message.tone === "success" ? "check-circle" : "alert"} size={15} />
          <span>{message.text}</span>
        </div>
      )}

      <div className="settings-grid">
        <nav className="settings-nav">
          {SECTIONS.map((item) => (
            <button key={item.key} type="button" className={`settings-nav-item ${section === item.key ? "on" : ""}`} onClick={() => setSection(item.key)}>
              {item.label}
            </button>
          ))}
        </nav>

        <div>
          {section === "profile" && (
            <div className="card settings-section">
              <h3>个人信息</h3>
              <p>展示在侧边栏和学习画像里的基础信息。</p>
              <div className="settings-row">
                <div className="settings-identity">
                  <div className="avatar-lg">{user.nickname.slice(0, 1).toUpperCase()}</div>
                  <div className="settings-meta"><strong>{user.nickname}</strong><span>{user.account}</span></div>
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-meta"><strong>昵称</strong><span>显示在学习记录和资料问答里</span></div>
                <div className="settings-control">
                  <input value={nickname} onChange={(event) => setNickname(event.target.value)} className="settings-input" />
                  <button className="outline-button" type="button" onClick={() => void saveNickname()} disabled={busy || nickname === user.nickname}>保存</button>
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-meta"><strong>账号</strong><span>注册于 {new Date(user.createdAt).toLocaleDateString("zh-CN")}</span></div>
                <span className="settings-static">{user.account}</span>
              </div>
            </div>
          )}

          {section === "notification" && (
            <div className="card settings-section">
              <h3>通知偏好</h3>
              <p>控制系统何时主动提醒你。</p>
              <div className="settings-row">
                <div className="settings-meta"><strong>到期复习提醒</strong><span>知识点到期时，主动出现在「今日学习」推荐里</span></div>
                <button type="button" className={`switch ${preferences.reviewDue ? "on" : ""}`} aria-pressed={preferences.reviewDue} onClick={() => savePreferences({ reviewDue: !preferences.reviewDue })} />
              </div>
              <div className="settings-row">
                <div className="settings-meta"><strong>每日学习提醒</strong><span>每天固定时间发送学习提醒</span></div>
                <button type="button" className={`switch ${preferences.dailyReminder ? "on" : ""}`} aria-pressed={preferences.dailyReminder} onClick={() => savePreferences({ dailyReminder: !preferences.dailyReminder })} />
              </div>
              <div className="settings-row">
                <div className="settings-meta"><strong>周学习总结</strong><span>每周日发送本周掌握度变化摘要</span></div>
                <button type="button" className={`switch ${preferences.weeklyDigest ? "on" : ""}`} aria-pressed={preferences.weeklyDigest} onClick={() => savePreferences({ weeklyDigest: !preferences.weeklyDigest })} />
              </div>
            </div>
          )}

          {section === "security" && (
            <div className="card settings-section">
              <h3>账号安全</h3>
              <p>管理登录方式与密码。</p>
              <div className="settings-row">
                <div className="settings-meta"><strong>登录密码</strong><span>定期更换可以提升账号安全性</span></div>
                <button className="outline-button" type="button" onClick={() => setShowPasswordForm((value) => !value)}>
                  {showPasswordForm ? "取消" : "修改密码"}
                </button>
              </div>
              {showPasswordForm && (
                <div className="settings-inline-form">
                  <label className="auth-field">
                    <span>当前密码</span>
                    <input type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} autoComplete="current-password" />
                  </label>
                  <label className="auth-field">
                    <span>新密码</span>
                    <input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} placeholder="至少 8 位" autoComplete="new-password" />
                  </label>
                  <button className="primary-button" type="button" onClick={() => void savePassword()} disabled={busy}>确认修改</button>
                </div>
              )}
              <div className="settings-row">
                <div className="settings-meta"><strong>退出登录</strong><span>退出后需要重新登录才能继续学习</span></div>
                <button className="danger-button" type="button" onClick={() => void logout()}><Icon name="log-out" size={15} />退出登录</button>
              </div>
            </div>
          )}

          {section === "privacy" && (
            <div className="card settings-section">
              <h3>数据与隐私</h3>
              <p>导出或清除你的学习数据。</p>
              <div className="settings-row">
                <div className="settings-meta"><strong>导出学习记录</strong><span>包含诊断结果、掌握度历史与学习事件</span></div>
                <button className="outline-button" type="button" onClick={() => notify("error", "后端导出接口（GET /learning-records/export）尚未接入。")}>
                  <Icon name="download" size={15} />导出为 CSV
                </button>
              </div>
              <div className="settings-row">
                <div className="settings-meta"><strong>删除账号</strong><span>将永久清除所有学习数据，不可恢复</span></div>
                <button className="danger-button" type="button" onClick={() => notify("error", "删除账号需要后端接口（DELETE /auth/account）支持，请谨慎操作。")}>
                  <Icon name="trash" size={15} />删除账号
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
