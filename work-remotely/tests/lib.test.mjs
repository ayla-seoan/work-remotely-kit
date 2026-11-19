// office/lib.js 의 순수 함수 테스트 — 실행: node --test tests/
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const lib = require("../office/lib.js");

const kangiScope = {
  member: "dev-kangi", projects: ["1"], coPeople: ["design-miyoung", "dev-jaemin", "po-seoan"],
  memberProjects: { "dev-kangi": ["1"], "dev-jaemin": ["1"], "po-seoan": ["1", "2"], "mkt-hyeopseong": ["2"], "design-miyoung": ["1"] },
  grants: { "작업 기록": ["mkt-hyeopseong"], "할 일": [], "이슈": [] }, taskIds: ["1", "5"], issueIds: ["1"],
};
const SNAP = {
  full: { name: "full", scope: null },
  public: { name: "public", scope: { member: "" } },
  views: { "dev-kangi": { name: "kangi", scope: kangiScope } },
  preview: null,
};

test("pickView: 관리자는 전체", () => {
  const r = lib.pickView(SNAP, { admin: true, member: "", viewAs: "" });
  assert.equal(r.mode, "full");
  assert.equal(r.D.name, "full");
});

test("pickView: 관리자 미리보기", () => {
  const r = lib.pickView(SNAP, { admin: true, member: "po-seoan", viewAs: "dev-kangi" });
  assert.equal(r.mode, "preview");
  assert.equal(r.D.name, "kangi");
  assert.equal(r.as, "dev-kangi");
});

test("pickView: 연결된 팀원", () => {
  const r = lib.pickView(SNAP, { admin: false, member: "dev-kangi", viewAs: "" });
  assert.equal(r.mode, "member");
  assert.equal(r.D.name, "kangi");
});

test("pickView: 연결됐지만 아직 스냅샷에 없는 사람은 공개 + 안내", () => {
  const r = lib.pickView(SNAP, { admin: false, member: "dev-new", viewAs: "" });
  assert.equal(r.mode, "public");
  assert.match(r.note, /다음 새로 고침/);
});

test("pickView: 모르는 사람 · 로그아웃은 공개", () => {
  assert.equal(lib.pickView(SNAP, null).mode, "public");
  assert.equal(lib.pickView(SNAP, { admin: false, member: "", viewAs: "" }).D.name, "public");
});

test("pickView: 팀원은 viewAs 를 써도 다른 사람 보기를 못 가져요", () => {
  const r = lib.pickView(SNAP, { admin: false, member: "", viewAs: "dev-kangi" });
  assert.equal(r.mode, "public");
});

test("pickView: 웹(Vercel) 판은 SNAP.note 를 안내로 써요", () => {
  const web = { full: null, public: null, views: {}, preview: { name: "f", scope: null }, note: "웹 공개 화면 · 읽기 전용" };
  const r = lib.pickView(web, null);
  assert.equal(r.mode, "full");
  assert.equal(r.note, "웹 공개 화면 · 읽기 전용");
});

test("remoteScreen: 401 로그인 · 403 미등록 · 200 앱 · 그 밖 오류", () => {
  assert.deepEqual(lib.remoteScreen(401, {}), { screen: "login" });
  assert.deepEqual(lib.remoteScreen(403, { error: "unregistered", email: "a@b.c" }), { screen: "unregistered", email: "a@b.c" });
  const body = { preview: { scope: null }, who: { email: "a@b.c", kind: "admin", id: "" } };
  const app = lib.remoteScreen(200, body);
  assert.equal(app.screen, "app");
  assert.equal(app.snap, body);
  assert.deepEqual(app.who, body.who);
  assert.deepEqual(lib.remoteScreen(500, {}), { screen: "error" });
  assert.deepEqual(lib.remoteScreen(200, null), { screen: "error" });
  assert.deepEqual(lib.remoteScreen(0, null), { screen: "error" });
});

test("remoteScreen: 503 no_data 는 '준비 중'", () => {
  assert.deepEqual(lib.remoteScreen(503, { error: "no_data" }), { screen: "preparing" });
});

test("loginNotice: 로그인 실패 이유를 쉬운 말로", () => {
  assert.match(lib.loginNotice("cancelled"), /취소/);
  assert.match(lib.loginNotice("state"), /다시/);
  assert.match(lib.loginNotice("failed"), /다시/);
  assert.equal(lib.loginNotice(""), "");
  assert.equal(lib.loginNotice(null), "");
});

test("pickView: 미리보기 파일은 들어 있는 보기 하나", () => {
  const one = { full: null, public: null, views: {}, preview: { name: "p", scope: kangiScope } };
  const r = lib.pickView(one, { admin: true, member: "", viewAs: "" });
  assert.equal(r.D.name, "p");
  assert.equal(r.mode, "member");
  assert.equal(lib.pickView({ ...one, preview: { name: "f", scope: null } }, null).mode, "full");
});

const taskById = { "1": { "프로젝트": "1", "담당자": "dev-kangi" }, "4": { "프로젝트": "2", "담당자": "mkt-hyeopseong" },
  "8": { "프로젝트": "2", "담당자": "po-seoan" } };

test("makeVisibility: 할 일은 프로젝트 · 본인 · 연 범위", () => {
  const vis = lib.makeVisibility(kangiScope, taskById);
  assert.equal(vis.task({ "프로젝트": "1", "담당자": "dev-jaemin" }), true);
  assert.equal(vis.task({ "프로젝트": "2", "담당자": "mkt-hyeopseong" }), false);
  assert.equal(vis.task({ "프로젝트": "", "담당자": "dev-kangi" }), true);   // 프로젝트 없는 새 노션 행, 내 것
  assert.equal(vis.task({ "프로젝트": "", "담당자": "mkt-hyeopseong" }), false);
});

test("makeVisibility: 이슈는 보고자도 봐요", () => {
  const vis = lib.makeVisibility(kangiScope, taskById);
  assert.equal(vis.issue({ "프로젝트": "", "담당자": "", "보고자": "dev-kangi" }), true);
  assert.equal(vis.issue({ "프로젝트": "", "담당자": "", "보고자": "mkt-hyeopseong" }), false);
});

test("makeVisibility: 작업 기록", () => {
  const vis = lib.makeVisibility(kangiScope, taskById);
  assert.equal(vis.log("dev-jaemin", ""), true);            // 같은 프로젝트 동료, 할 일 번호 없음
  assert.equal(vis.log("po-seoan", "8"), false);            // 다른 프로젝트 할 일
  assert.equal(vis.log("po-seoan", "1"), true);
  assert.equal(vis.log("mkt-hyeopseong", "4"), true);       // 연 범위
  assert.equal(vis.log("design-minjeong", ""), false);
  assert.equal(vis.checkin("dev-jaemin"), true);
  assert.equal(vis.checkin("design-minjeong"), false);
});

test("romanizeGiven: 성은 빼고 로마자 표기법", () => {
  assert.equal(lib.romanizeGiven("김강이"), "gangi");
  assert.equal(lib.romanizeGiven("차명근"), "myeonggeun");
  assert.equal(lib.romanizeGiven("이민정"), "minjeong");
  assert.equal(lib.romanizeGiven("신협성"), "hyeopseong");
  assert.equal(lib.romanizeGiven("김서안"), "seoan");
  assert.equal(lib.romanizeGiven("김재민"), "jaemin");
  assert.equal(lib.romanizeGiven(" 김 새봄 "), "saebom");
  assert.equal(lib.romanizeGiven("Kim"), "");
});

test("suggestMemberId: 직군 키 + 이름, 겹치면 숫자", () => {
  assert.equal(lib.suggestMemberId("dev", "김강이", []), "dev-gangi");
  assert.equal(lib.suggestMemberId("dev", "김강이", ["dev-gangi"]), "dev-gangi2");
  assert.equal(lib.suggestMemberId("dev", "김강이", ["dev-gangi", "dev-gangi2"]), "dev-gangi3");
  assert.equal(lib.suggestMemberId("design", "Kim", []), "");
});

test("isGithubLogin · isMemberId", () => {
  assert.equal(lib.isGithubLogin("ayla-seoan"), true);
  assert.equal(lib.isGithubLogin("a1"), true);
  assert.equal(lib.isGithubLogin("-bad"), false);
  assert.equal(lib.isGithubLogin("bad-"), false);
  assert.equal(lib.isGithubLogin("a--b"), false);
  assert.equal(lib.isGithubLogin("a".repeat(40)), false);
  assert.equal(lib.isGithubLogin("a".repeat(39)), true);
  assert.equal(lib.isMemberId("dev-gangi2"), true);
  assert.equal(lib.isMemberId("Dev-X"), false);
  assert.equal(lib.isMemberId("dev-"), false);
});

test("makeVisibility: 관리자 전체 · 공개", () => {
  const all = lib.makeVisibility(null, taskById);
  assert.equal(all.log("anyone", "8"), true);
  assert.equal(all.task({ "프로젝트": "2" }), true);
  const none = lib.makeVisibility({ member: "", projects: [], coPeople: [], memberProjects: {}, grants: {} }, taskById);
  assert.equal(none.log("dev-kangi", ""), false);
  assert.equal(none.task({ "프로젝트": "1", "담당자": "dev-kangi" }), false);
});
