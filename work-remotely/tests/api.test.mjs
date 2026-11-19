// Vercel 함수 공용 모듈(api/_lib.js) 테스트 — 실행: node --test "tests/*.test.mjs"
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const L = require("../../api/_lib.js");
const SECRET = "test-secret-1234567890";

test("세션: 서명 → 확인 왕복, 위조 · 만료는 거절", () => {
  const now = Date.UTC(2026, 10, 19);
  const c = L.signSession("Kangi@Example.com", SECRET, now);
  assert.deepEqual(L.verifySession(c, SECRET, now + 1000), { email: "kangi@example.com" });
  const forged = c.slice(0, -1) + (c.endsWith("A") ? "B" : "A");
  assert.equal(L.verifySession(forged, SECRET, now), null);
  assert.equal(L.verifySession(c, "other-secret", now), null);
  assert.equal(L.verifySession(c, SECRET, now + 8 * 24 * 3600 * 1000), null);
  assert.equal(L.verifySession("", SECRET, now), null);
  assert.equal(L.verifySession(undefined, SECRET, now), null);
});

test("이메일 해시는 파이썬 email_hash 와 같아요", () => {
  assert.equal(L.emailHash(" Admin@Example.com "), "258d8dc916db8cea2cafb6c3cd0cb0246efe061421dbd83ec3a350428cabda4f");
});

test("보기 고르기: 관리자가 이기고, 등록된 이메일은 팀원, 나머지는 미등록", () => {
  const h = L.emailHash("admin@example.com");
  const cfg = { admins: ["ADMIN@example.com"], accounts: { [h]: "po-seoan", [L.emailHash("k@x.io")]: "dev-kangi" } };
  assert.deepEqual(L.chooseView("admin@example.com", cfg), { kind: "admin" });
  assert.deepEqual(L.chooseView("K@X.io", cfg), { kind: "member", id: "dev-kangi" });
  assert.deepEqual(L.chooseView("who@x.io", cfg), { kind: "unregistered" });
});

test("state: 둘 다 있고 같을 때만", () => {
  assert.equal(L.checkState("a1", "a1"), true);
  assert.equal(L.checkState("a1", "b2"), false);
  assert.equal(L.checkState(undefined, "a1"), false);
  assert.equal(L.checkState("", ""), false);
});

const b64 = (o) => Buffer.from(JSON.stringify(o)).toString("base64url");
const jwt = (payload) => `${b64({ alg: "RS256" })}.${b64(payload)}.sig`;

test("id_token: aud · iss · exp · email_verified 확인", () => {
  const now = Date.UTC(2026, 10, 19);
  const ok = { aud: "cid", iss: "https://accounts.google.com", exp: now / 1000 + 600, email: "A@B.co", email_verified: true };
  assert.deepEqual(L.parseIdToken(jwt(ok), "cid", now), { email: "a@b.co" });
  assert.equal(L.parseIdToken(jwt({ ...ok, iss: "accounts.google.com" }), "cid", now)?.email, "a@b.co");
  assert.equal(L.parseIdToken(jwt({ ...ok, aud: "other" }), "cid", now), null);
  assert.equal(L.parseIdToken(jwt({ ...ok, exp: now / 1000 - 1 }), "cid", now), null);
  assert.equal(L.parseIdToken(jwt({ ...ok, email_verified: false }), "cid", now), null);
  assert.equal(L.parseIdToken(jwt({ ...ok, iss: "evil" }), "cid", now), null);
  assert.equal(L.parseIdToken("garbage", "cid", now), null);
});

test("/api/data: 로그인 없음 401 · 미등록 403 · 팀원 · 관리자 200", async () => {
  const fs = await import("node:fs");
  const os = await import("node:os");
  const path = await import("node:path");
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "wrapi-"));
  const api = path.join(dir, "work-remotely", "web-api");
  fs.mkdirSync(path.join(api, "views"), { recursive: true });
  fs.writeFileSync(path.join(api, "views", "dev-kangi.json"), JSON.stringify({ preview: { scope: { member: "dev-kangi" } } }));
  fs.writeFileSync(path.join(api, "full.json"), JSON.stringify({ preview: { scope: null } }));
  fs.writeFileSync(path.join(api, "accounts.json"), JSON.stringify({ [L.emailHash("k@x.io")]: "dev-kangi" }));
  const cwd = process.cwd();
  process.chdir(dir);
  process.env.SESSION_SECRET = SECRET;
  process.env.ADMIN_EMAILS = "boss@x.io";
  const handler = require("../../api/data.js");
  const call = (email) => {
    const headers = {};
    const res = { statusCode: 0, body: "", setHeader: (k, v) => { headers[k] = v; }, getHeader: (k) => headers[k], end: (b) => { res.body = b || ""; } };
    handler({ url: "/api/data", headers: email ? { cookie: `wr_session=${encodeURIComponent(L.signSession(email, SECRET))}` } : {} }, res);
    return { status: res.statusCode, body: res.body ? JSON.parse(res.body) : null, headers };
  };
  try {
    assert.equal(call(null).status, 401);
    const un = call("who@x.io");
    assert.equal(un.status, 403);
    assert.equal(un.body.email, "who@x.io");
    const kangi = call("K@x.io");
    assert.equal(kangi.status, 200);
    assert.equal(kangi.body.preview.scope.member, "dev-kangi");
    assert.deepEqual(kangi.body.who, { email: "k@x.io", kind: "member", id: "dev-kangi" });
    assert.equal(kangi.headers["Cache-Control"], "private, no-store");
    const boss = call("boss@x.io");
    assert.equal(boss.status, 200);
    assert.equal(boss.body.preview.scope, null);
  } finally {
    process.chdir(cwd);
  }
});

test("/api/callback: 취소 · state 불일치는 원시 JSON 대신 첫 화면 안내로 보내요", async () => {
  process.env.GOOGLE_CLIENT_ID = "cid";
  process.env.GOOGLE_CLIENT_SECRET = "sec";
  process.env.PUBLIC_URL = "https://example.vercel.app";
  process.env.SESSION_SECRET = SECRET;
  const handler = require("../../api/callback.js");
  const call = async (url, cookie) => {
    const headers = {};
    const res = { statusCode: 0, setHeader: (k, v) => { headers[k] = v; }, getHeader: (k) => headers[k], end: () => {} };
    await handler({ url, headers: cookie ? { cookie } : {} }, res);
    return { status: res.statusCode, headers };
  };
  const cancelled = await call("/api/callback?error=access_denied&state=s1", "wr_state=s1");
  assert.equal(cancelled.status, 302);
  assert.equal(cancelled.headers.Location, "/?login_error=cancelled");
  const bad = await call("/api/callback?code=c&state=s2", "wr_state=s1");
  assert.equal(bad.headers.Location, "/?login_error=state");
  assert.ok(!String(bad.headers["Set-Cookie"]).includes("wr_session=e"));
});

test("쿠키 읽기", () => {
  assert.deepEqual(L.readCookies({ headers: { cookie: "a=1; wr_session=x.y; b=%20z" } }), { a: "1", wr_session: "x.y", b: " z" });
  assert.deepEqual(L.readCookies({ headers: {} }), {});
});
