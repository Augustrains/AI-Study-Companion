/**
 * 会话与身份认证服务层
 * --------------------------------------------------------------------------
 * 设计原则与 services/api.ts 保持一致：
 *   1. 真实接口路径已在 authEndpoints 中预留，后端实现后无需改动页面组件；
 *   2. 后端尚未提供认证模块时，自动降级为本地会话（localStorage），
 *      保证登录/注册流程现在就能跑通、联调时再无缝切换；
 *   3. 页面组件只依赖本文件导出的方法，不直接拼接请求。
 *
 * 【后端接入清单】实现以下接口后，降级逻辑会自动失效，无需修改前端：
 *   POST /api/auth/register   { nickname, account, password }        -> AuthSession
 *   POST /api/auth/login      { account, password }                  -> AuthSession
 *   POST /api/auth/login-code { account, code }                      -> AuthSession
 *   POST /api/auth/send-code  { account, scene }                     -> { sent: true }
 *   POST /api/auth/logout     {}                                     -> 204
 *   GET  /api/auth/me                                                -> AuthUser
 *   PATCH /api/auth/profile   { nickname? , avatarColor? }           -> AuthUser
 *   PATCH /api/auth/password  { currentPassword, newPassword }       -> 204
 */

export type AuthUser = {
  userId: string;
  nickname: string;
  account: string;
  createdAt: string;
  /** 后端可选返回；前端仅用于展示 */
  streakDays?: number;
};

export type AuthSession = { token: string; user: AuthUser };
export type AuthError = { code: string; message: string; retryable?: boolean };

/**
 * 内置体验账号。
 * userId 固定为 demo_user，与后端 scripts/seed_demo_data.py 写入的演示数据保持一致，
 * 因此登录后能直接看到诊断记录、掌握度、学习计划和到期复习项。
 * 账号密码见项目根目录 README.md。后端认证模块上线后，这段降级逻辑不再生效。
 */
export const DEMO_ACCOUNT = {
  userId: "demo_user",
  nickname: "体验账号",
  account: "demo@study.local",
  password: "demo1234",
} as const;

const SESSION_KEY = "study-companion.session";
const LOCAL_ACCOUNTS_KEY = "study-companion.local-accounts";
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

/** 与 api.ts 相同的开关：显式关闭时全程使用本地模拟。 */
const USE_REAL_API = import.meta.env.VITE_USE_REAL_API !== "false";

export const authEndpoints = {
  register: "/auth/register",
  login: "/auth/login",
  loginByCode: "/auth/login-code",
  sendCode: "/auth/send-code",
  logout: "/auth/logout",
  me: "/auth/me",
  profile: "/auth/profile",
  password: "/auth/password",
} as const;

/* ========================= 会话读写 ========================= */

let memorySession: AuthSession | null = null;

export function getSession(): AuthSession | null {
  if (memorySession) return memorySession;
  try {
    const raw = window.localStorage.getItem(SESSION_KEY);
    memorySession = raw ? (JSON.parse(raw) as AuthSession) : null;
  } catch {
    memorySession = null;
  }
  return memorySession;
}

function saveSession(session: AuthSession | null) {
  memorySession = session;
  try {
    if (session) window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
    else window.localStorage.removeItem(SESSION_KEY);
  } catch {
    // 隐私模式下 localStorage 不可用时，仅保留内存态。
  }
}

/**
 * 当前登录用户 ID。services/api.ts 用它替换原先写死的 "user_001"，
 * 未登录时回退到该默认值，保证既有演示数据仍可访问。
 */
export function getCurrentUserId(): string {
  return getSession()?.user.userId ?? "user_001";
}

export function getCurrentUser(): AuthUser | null {
  return getSession()?.user ?? null;
}

/** 供 api.ts 注入到请求头，后端启用鉴权后即可直接读取。 */
export function getAuthHeaders(): Record<string, string> {
  const token = getSession()?.token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/* ========================= 请求封装 ========================= */

/** 后端未实现该接口（404/405/501）时抛出，用于触发本地降级。 */
class EndpointMissingError extends Error {}

async function authRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json", ...getAuthHeaders(), ...init?.headers },
      ...init,
    });
  } catch {
    // 网络层失败：无法判定后端是否实现，交由上层降级处理。
    throw new EndpointMissingError("network unreachable");
  }
  if (response.status === 404 || response.status === 405 || response.status === 501) {
    throw new EndpointMissingError(`auth endpoint not implemented: ${path}`);
  }
  if (!response.ok) {
    const parsed = (await response.json().catch(() => null)) as AuthError | null;
    throw parsed ?? { code: `HTTP_${response.status}`, message: "请求失败，请稍后重试。", retryable: response.status >= 500 };
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

/* ===================== 本地降级实现（后端认证上线前的过渡） ===================== */

type LocalAccount = { userId: string; nickname: string; account: string; passwordHash: string; createdAt: string };

/**
 * 仅用于后端认证接口就绪前的本地联调。
 * 真实的凭据校验必须在服务端完成，这里做散列只是为了不落地明文。
 */
async function hashPassword(password: string): Promise<string> {
  const data = new TextEncoder().encode(`study-companion::${password}`);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

function readLocalAccounts(): LocalAccount[] {
  try {
    const raw = window.localStorage.getItem(LOCAL_ACCOUNTS_KEY);
    return raw ? (JSON.parse(raw) as LocalAccount[]) : [];
  } catch {
    return [];
  }
}

function writeLocalAccounts(accounts: LocalAccount[]) {
  try {
    window.localStorage.setItem(LOCAL_ACCOUNTS_KEY, JSON.stringify(accounts));
  } catch {
    // 忽略：本地降级模式下写入失败不阻断流程。
  }
}

const toUser = (account: LocalAccount): AuthUser => ({
  userId: account.userId,
  nickname: account.nickname,
  account: account.account,
  createdAt: account.createdAt,
});

const localSession = (account: LocalAccount): AuthSession => ({
  token: `local.${account.userId}`,
  user: toUser(account),
});

const demoLocalAccount = (): LocalAccount => ({
  userId: DEMO_ACCOUNT.userId,
  nickname: DEMO_ACCOUNT.nickname,
  account: DEMO_ACCOUNT.account,
  passwordHash: "",
  createdAt: "2026-01-01T00:00:00.000Z",
});

const localAuth = {
  async register(payload: { nickname: string; account: string; password: string }): Promise<AuthSession> {
    const accounts = readLocalAccounts();
    if (accounts.some((item) => item.account === payload.account)) {
      throw { code: "ACCOUNT_EXISTS", message: "该邮箱或手机号已注册，请直接登录。" } satisfies AuthError;
    }
    const account: LocalAccount = {
      userId: `local_${Date.now().toString(36)}`,
      nickname: payload.nickname,
      account: payload.account,
      passwordHash: await hashPassword(payload.password),
      createdAt: new Date().toISOString(),
    };
    writeLocalAccounts([...accounts, account]);
    return localSession(account);
  },
  async login(payload: { account: string; password: string }): Promise<AuthSession> {
    // 体验账号：固定凭据，无需注册。
    if (payload.account === DEMO_ACCOUNT.account && payload.password === DEMO_ACCOUNT.password) {
      return localSession(demoLocalAccount());
    }
    const accounts = readLocalAccounts();
    const found = accounts.find((item) => item.account === payload.account);
    if (!found || found.passwordHash !== (await hashPassword(payload.password))) {
      throw { code: "INVALID_CREDENTIALS", message: "账号或密码不正确。" } satisfies AuthError;
    }
    return localSession(found);
  },
  async loginByCode(payload: { account: string; code: string }): Promise<AuthSession> {
    if (payload.account === DEMO_ACCOUNT.account && payload.code.trim().length >= 4) {
      return localSession(demoLocalAccount());
    }
    const accounts = readLocalAccounts();
    const found = accounts.find((item) => item.account === payload.account);
    if (!found) throw { code: "ACCOUNT_NOT_FOUND", message: "该账号尚未注册，请先创建账号。" } satisfies AuthError;
    if (payload.code.trim().length < 4) throw { code: "INVALID_CODE", message: "验证码不正确。" } satisfies AuthError;
    return localSession(found);
  },
  async updateProfile(patch: { nickname?: string }): Promise<AuthUser> {
    const session = getSession();
    if (!session) throw { code: "UNAUTHENTICATED", message: "请先登录。" } satisfies AuthError;
    const accounts = readLocalAccounts();
    const next = accounts.map((item) => (item.userId === session.user.userId ? { ...item, ...patch } : item));
    writeLocalAccounts(next);
    return { ...session.user, ...patch };
  },
  async updatePassword(payload: { currentPassword: string; newPassword: string }): Promise<void> {
    const session = getSession();
    if (!session) throw { code: "UNAUTHENTICATED", message: "请先登录。" } satisfies AuthError;
    const accounts = readLocalAccounts();
    const found = accounts.find((item) => item.userId === session.user.userId);
    if (!found || found.passwordHash !== (await hashPassword(payload.currentPassword))) {
      throw { code: "INVALID_CREDENTIALS", message: "当前密码不正确。" } satisfies AuthError;
    }
    found.passwordHash = await hashPassword(payload.newPassword);
    writeLocalAccounts(accounts);
  },
};

/** 真实接口不可用时是否已降级过，用于在设置页提示当前认证模式。 */
let usingLocalFallback = !USE_REAL_API;
export const isLocalAuthFallback = () => usingLocalFallback;

async function withFallback<T>(remote: () => Promise<T>, local: () => Promise<T>): Promise<T> {
  if (!USE_REAL_API) return local();
  try {
    return await remote();
  } catch (error) {
    if (error instanceof EndpointMissingError) {
      usingLocalFallback = true;
      return local();
    }
    throw error;
  }
}

/* ========================= 对外方法 ========================= */

export const auth = {
  async register(payload: { nickname: string; account: string; password: string }): Promise<AuthSession> {
    const session = await withFallback(
      () => authRequest<AuthSession>(authEndpoints.register, { method: "POST", body: JSON.stringify(payload) }),
      () => localAuth.register(payload),
    );
    saveSession(session);
    return session;
  },

  async login(payload: { account: string; password: string }): Promise<AuthSession> {
    const session = await withFallback(
      () => authRequest<AuthSession>(authEndpoints.login, { method: "POST", body: JSON.stringify(payload) }),
      () => localAuth.login(payload),
    );
    saveSession(session);
    return session;
  },

  async loginByCode(payload: { account: string; code: string }): Promise<AuthSession> {
    const session = await withFallback(
      () => authRequest<AuthSession>(authEndpoints.loginByCode, { method: "POST", body: JSON.stringify(payload) }),
      () => localAuth.loginByCode(payload),
    );
    saveSession(session);
    return session;
  },

  /**
   * 请求登录验证码。
   * 后端开发模式（AUTH_EXPOSE_CODE!=false）会把验证码放在 devCode 里直接返回，
   * 由登录页显示在屏幕上；上线时后端把该字段置空、改由邮件/短信送达，前端不需要改。
   */
  async sendLoginCode(account: string): Promise<{ sent: boolean; fallback: boolean; devCode?: string }> {
    return withFallback<{ sent: boolean; fallback: boolean; devCode?: string }>(
      async () => {
        const result = await authRequest<{ sent: boolean; devCode?: string | null; delivery?: string }>(
          authEndpoints.sendCode,
          { method: "POST", body: JSON.stringify({ account, scene: "login" }) },
        );
        return { sent: result?.sent ?? true, fallback: false, devCode: result?.devCode ?? undefined };
      },
      // 本地降级：不真正发送，仅提示后端接口尚未接入。
      async () => ({ sent: true, fallback: true }),
    );
  },

  async logout(): Promise<void> {
    if (USE_REAL_API) {
      await authRequest(authEndpoints.logout, { method: "POST" }).catch(() => undefined);
    }
    saveSession(null);
  },

  async updateProfile(patch: { nickname?: string }): Promise<AuthUser> {
    const user = await withFallback(
      () => authRequest<AuthUser>(authEndpoints.profile, { method: "PATCH", body: JSON.stringify(patch) }),
      () => localAuth.updateProfile(patch),
    );
    const session = getSession();
    if (session) saveSession({ ...session, user });
    return user;
  },

  async updatePassword(payload: { currentPassword: string; newPassword: string }): Promise<void> {
    await withFallback(
      () => authRequest<void>(authEndpoints.password, { method: "PATCH", body: JSON.stringify(payload) }),
      () => localAuth.updatePassword(payload),
    );
  },
};
