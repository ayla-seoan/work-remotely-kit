/* 오피스 화면 공용 순수 함수 (export_office.py 가 template 의 자리에 그대로 넣어요).
   node 테스트: node --test "tests/*.test.mjs" */

/* 누가 보느냐에 따라 스냅샷 하나를 골라요.
   SNAP = {full, public, views: {아이디: 스냅샷}, preview}
   who  = {admin, member, viewAs} 또는 null (로그인 정보 없음) */
function pickView(SNAP, who) {
  const w = who || { admin: false, member: "", viewAs: "" };
  if (SNAP.preview) {
    const sc = SNAP.preview.scope;
    return { D: SNAP.preview, mode: sc == null ? "full" : sc.member ? "member" : "public", as: sc && sc.member || "", note: SNAP.note || "미리보기 파일이에요" };
  }
  const views = SNAP.views || {};
  if (w.admin) {
    if (w.viewAs && views[w.viewAs]) return { D: views[w.viewAs], mode: "preview", as: w.viewAs, note: "" };
    return { D: SNAP.full, mode: "full", as: "", note: "" };
  }
  if (w.member && views[w.member]) return { D: views[w.member], mode: "member", as: w.member, note: "" };
  return {
    D: SNAP.public, mode: "public", as: "",
    note: w.member ? "다음 새로 고침 뒤에 내 프로젝트 내역이 보여요" : "관리자가 계정을 연결하면 내 프로젝트 내역이 보여요",
  };
}

/* 화면에서 바로 생기는 데이터(실시간 기록 · 노션 · 기간 연장)를 거르는 판정. 규칙은 visibility.py 와 같아요.
   scope 가 null 이면 관리자 전체 보기 → 모두 보여요. taskById = {번호: {프로젝트, 담당자}} */
function makeVisibility(scope, taskById) {
  if (scope == null) {
    const yes = () => true;
    return { log: yes, task: yes, issue: yes, checkin: yes };
  }
  const v = scope.member || "";
  const projects = scope.projects || [];
  const co = scope.coPeople || [];
  const mp = scope.memberProjects || {};
  const grants = scope.grants || {};
  const granted = (item, person) => !!person && ((grants[item] || []).includes(person) || (grants[item] || []).includes("전원"));
  const checkin = (person) => !!v && (person === v || co.includes(person) || granted("작업 기록", person));
  return {
    checkin,
    log(person, taskId) {
      if (!v) return false;
      if (person === v || granted("작업 기록", person)) return true;
      if (taskId) {
        const proj = (taskById[taskId] || {})["프로젝트"] || "";
        return !!proj && projects.includes(proj) && (mp[person] || []).includes(proj);
      }
      return co.includes(person);
    },
    task(row) {
      if (!v) return false;
      const owner = row["담당자"] || "";
      return projects.includes(row["프로젝트"] || "") || owner === v || granted("할 일", owner);
    },
    issue(row) {
      if (!v) return false;
      const owner = row["담당자"] || "";
      return projects.includes(row["프로젝트"] || "") || owner === v || row["보고자"] === v || granted("이슈", owner);
    },
  };
}

/* 팀원 아이디 제안: 성(첫 글자)은 빼고 국어의 로마자 표기법을 글자마다 (받침이 이어지는 소리 변화는 무시) */
const RR_INITIAL = ["g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h"];
const RR_VOWEL = ["a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo", "u", "wo", "we", "wi", "yu", "eu", "ui", "i"];
const RR_FINAL = ["", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l", "p", "l", "m", "p", "p", "t", "t", "ng", "t", "t", "k", "t", "p", "t"];
function romanizeGiven(name) {
  const syl = [...String(name || "")].filter((c) => c >= "가" && c <= "힣");
  return syl.slice(1).map((c) => {
    const n = c.charCodeAt(0) - 0xac00;
    return RR_INITIAL[Math.floor(n / 588)] + RR_VOWEL[Math.floor((n % 588) / 28)] + RR_FINAL[n % 28];
  }).join("");
}
const MEMBER_ID_RE = /^[a-z]+-[a-z0-9]+$/;
const GITHUB_RE = /^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$/;
const isMemberId = (s) => MEMBER_ID_RE.test(String(s || ""));
const isGithubLogin = (s) => GITHUB_RE.test(String(s || ""));
function suggestMemberId(roleKey, name, existing) {
  const given = romanizeGiven(name);
  if (!given || !roleKey) return "";
  const taken = new Set(existing || []);
  const base = `${roleKey}-${given}`;
  if (!taken.has(base)) return base;
  for (let i = 2; ; i += 1) if (!taken.has(`${base}${i}`)) return `${base}${i}`;
}

/* 웹(Vercel) 판: /api/data 응답 → 어떤 화면을 그릴지 */
function remoteScreen(status, body) {
  if (status === 401) return { screen: "login" };
  if (status === 403 && body && body.error === "unregistered") return { screen: "unregistered", email: body.email || "" };
  if (status === 200 && body && body.preview) return { screen: "app", snap: body, who: body.who || null };
  if (status === 503 && body && body.error === "no_data") return { screen: "preparing" };
  return { screen: "error" };
}

/* 구글 로그인에서 돌아왔는데 실패했을 때 (/?login_error=…) 보여 줄 한 줄 */
function loginNotice(code) {
  return {
    cancelled: "로그인을 취소했어요. 다시 하려면 아래 버튼을 눌러 주세요.",
    state: "로그인 시간이 지났거나 다른 창에서 시작했어요. 다시 로그인해 주세요.",
    failed: "구글 로그인을 확인하지 못했어요. 다시 로그인해 주세요.",
  }[code || ""] || "";
}

if (typeof module !== "undefined") module.exports = { pickView, makeVisibility, romanizeGiven, suggestMemberId, isGithubLogin, isMemberId, remoteScreen, loginNotice };
