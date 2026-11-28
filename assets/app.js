// AI-Tech Radar — 화면 로직(빌드 도구 없이 동작하는 ES 모듈)
import { buildLexicon, parseQuery, prepareHaystack, matchScore, highlight, escHTML } from './search.js';

const $ = (s, el = document) => el.querySelector(s);
const TYPES = [['news', '뉴스'], ['paper', '논문'], ['patent', '특허']];
const TYPE_LABEL = Object.fromEntries(TYPES);
const PERIODS = [['today', '오늘'], ['3d', '3일'], ['7d', '7일'], ['30d', '30일'], ['all', '전체'], ['custom', '기간 지정']];
const SORTS = ['latest', 'relevance', 'hot'];
const PAGE = 30;
const DEFAULT_PERIOD = '7d';

const S = { tab: 'all', cat: [], period: DEFAULT_PERIOD, q: '', sort: 'latest', from: '', to: '', saved: false };
let ITEMS = [];
let META = {};
let TAX = { categories: [], fallback: { key: 'etc', label: '일반·기타', short: '기타' }, synonyms: [] };
let LEX = new Map();
let CATS = [];                       // [{key,label,short}] (기타 포함)
let CAT = {};                        // key → 정의
let parsed = null;
let shown = PAGE;
let archive = 'idle';                // idle | loading | done | error
let firstPaint = true;

// ── 저장소(브라우저별) ─────────────────────────────────────
const ls = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* 저장 불가 환경 */ } },
};
const saved = new Set(ls.get('atr.saved', []));
const prevVisit = ls.get('atr.lastVisit', 0);
setTimeout(() => ls.set('atr.lastVisit', Date.now()), 4000);

// ── 날짜(한국 시간 기준) ───────────────────────────────────
const fmtDay = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' });
const fmtTime = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: false });
const fmtWeek = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', weekday: 'short' });
const dayOf = (ms) => fmtDay.format(ms);
const today = () => dayOf(Date.now());
const toMs = (day) => Date.parse(`${day}T12:00:00+09:00`);
const addDays = (day, n) => dayOf(toMs(day) + n * 86400000);
const md = (day) => `${+day.slice(5, 7)}월 ${+day.slice(8, 10)}일`;

function dayTitle(day) {
  const t = today();
  const wk = fmtWeek.format(toMs(day));
  if (day === t) return ['오늘', `${md(day)} ${wk}`];
  if (day === addDays(t, -1)) return ['어제', `${md(day)} ${wk}`];
  return [`${md(day)} (${wk})`, day.slice(0, 4) !== t.slice(0, 4) ? day.slice(0, 4) + '년' : ''];
}

function when(it, grouped) {
  if (it.type === 'patent') return grouped ? '공개' : `공개 ${it._day.slice(5).replace('-', '.')}`;
  const diff = Date.now() - it._t;
  if (diff < 0) return '방금';
  if (diff < 3600e3) return `${Math.max(1, Math.round(diff / 60e3))}분 전`;
  if (diff < 86400e3) return `${Math.round(diff / 3600e3)}시간 전`;
  return grouped ? fmtTime.format(it._t) : `${it._day.slice(5).replace('-', '.')} ${fmtTime.format(it._t)}`;
}

// ── 주소창 상태(공유 가능한 링크) ──────────────────────────
function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  const tab = p.get('tab');
  S.tab = ['news', 'paper', 'patent'].includes(tab) ? tab : 'all';
  S.cat = (p.get('cat') || '').split(',').map((s) => s.trim()).filter(Boolean);
  S.from = p.get('from') || '';
  S.to = p.get('to') || '';
  const per = p.get('period');
  S.period = PERIODS.some(([k]) => k === per) ? per : (S.from || S.to ? 'custom' : DEFAULT_PERIOD);
  S.q = p.get('q') || '';
  S.sort = SORTS.includes(p.get('sort')) ? p.get('sort') : 'latest';
  S.saved = p.get('saved') === '1';
}
function writeHash() {
  const kv = [];
  const put = (k, v) => kv.push(`${k}=${encodeURIComponent(v).replace(/%2C/g, ',')}`);
  if (S.tab !== 'all') put('tab', S.tab);
  if (S.cat.length) put('cat', S.cat.join(','));
  if (S.period !== DEFAULT_PERIOD) put('period', S.period);
  if (S.period === 'custom') { if (S.from) put('from', S.from); if (S.to) put('to', S.to); }
  if (S.q.trim()) put('q', S.q.trim());
  if (S.sort !== 'latest') put('sort', S.sort);
  if (S.saved) put('saved', '1');
  const h = kv.join('&');
  try { history.replaceState(null, '', h ? `#${h}` : location.pathname + location.search); } catch { /* 샌드박스 */ }
}

// ── 데이터 ────────────────────────────────────────────────
async function getJSON(path) {
  const r = await fetch(path, { cache: 'no-cache' });
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  return r.json();
}

function setTaxonomy(tax) {
  if (tax && Array.isArray(tax.categories)) TAX = tax;
  CATS = [...TAX.categories.map(({ key, label, short }) => ({ key, label, short })), TAX.fallback];
  CAT = Object.fromEntries(CATS.map((c) => [c.key, c]));
  LEX = buildLexicon(TAX.synonyms || []);
}

function ingest(list) {
  const have = new Set(ITEMS.map((i) => i.id));
  for (const it of list || []) {
    if (!it || !it.id || have.has(it.id)) continue;
    have.add(it.id);
    it._t = Date.parse(it.date) || Date.now();
    it._day = dayOf(it._t);
    it._added = Date.parse(it.added || it.date) || it._t;
    it.cats = it.cats && it.cats.length ? it.cats : ['etc'];
    const catText = it.cats.map((c) => CAT[c] ? CAT[c].label : '').join(' ');
    prepareHaystack(it, catText);
    ITEMS.push(it);
  }
  ITEMS.sort((a, b) => b._t - a._t);
}

// ── 필터 계산 ─────────────────────────────────────────────
function range() {
  const t = today();
  switch (S.period) {
    case 'today': return [t, t];
    case '3d': return [addDays(t, -2), t];
    case '7d': return [addDays(t, -6), t];
    case '30d': return [addDays(t, -29), t];
    case 'custom': return [S.from || '0000-01-01', S.to || '9999-12-31'];
    default: return null;
  }
}
const needsArchive = () => {
  const r = range();
  return !r || r[0] < addDays(today(), -((META.recent_days || 7) - 1)) || !!S.q.trim() || S.saved;
};

function hotness(it) {
  if (it.type === 'paper') return (it.upvotes || 0) + (it.hf ? 5 : 0);
  if (it.type === 'news') return (it.also ? it.also.length : 0) * 12;
  return 0;
}

function compute() {
  parsed = S.q.trim() ? parseQuery(S.q, LEX) : null;
  const r = range();
  const tabOK = (it) => S.tab === 'all' || it.type === S.tab;
  const catOK = (it) => !S.cat.length || it.cats.some((c) => S.cat.includes(c));
  const perOK = (it) => !r || (it._day >= r[0] && it._day <= r[1]);

  const base = [];
  for (const it of ITEMS) {
    if (S.saved && !saved.has(it.id)) continue;
    const sc = parsed ? matchScore(it, parsed) : 1;
    if (!sc) continue;
    it._score = sc;
    base.push(it);
  }
  const typeCount = { all: 0, news: 0, paper: 0, patent: 0 };
  const catCount = Object.fromEntries(CATS.map((c) => [c.key, 0]));
  const radar = Object.fromEntries(TYPES.map(([t]) => [t, Object.fromEntries(CATS.map((c) => [c.key, 0]))]));
  const t0 = today();
  const days = Array.from({ length: 14 }, (_, i) => ({ day: addDays(t0, i - 13), news: 0, paper: 0, patent: 0 }));
  const dayIdx = Object.fromEntries(days.map((d, i) => [d.day, i]));
  const list = [];

  for (const it of base) {
    const a = tabOK(it), b = catOK(it), c = perOK(it);
    if (b && c) { typeCount.all++; typeCount[it.type]++; }
    if (a && c) for (const k of it.cats) { if (k in catCount) { catCount[k]++; radar[it.type][k]++; } }
    if (a && b && it._day in dayIdx) days[dayIdx[it._day]][it.type]++;
    if (a && b && c) list.push(it);
  }

  if (S.sort === 'relevance' && parsed) list.sort((x, y) => y._score - x._score || y._t - x._t);
  else if (S.sort === 'hot') list.sort((x, y) => hotness(y) - hotness(x) || y._t - x._t);
  else list.sort((x, y) => y._t - x._t);
  return { list, typeCount, catCount, radar, days };
}

// ── 그리기 ────────────────────────────────────────────────
const ICON_X = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';
const ICON_STAR = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>';

function renderTabs(tc) {
  const btn = (key, label) => `<button type="button" role="tab" ${key !== 'all' ? `data-type="${key}"` : ''} data-tab="${key}"
    aria-selected="${S.tab === key}">${label}<span class="n">${tc[key].toLocaleString('ko-KR')}</span></button>`;
  $('#tabs').innerHTML = btn('all', '전체') + TYPES.map(([k, l]) => btn(k, l)).join('');
}

function renderPeriods() {
  $('#periods').innerHTML = PERIODS.map(([k, l]) =>
    `<button type="button" class="chip" data-period="${k}" aria-pressed="${S.period === k}">${l}</button>`).join('');
  $('#range').hidden = S.period !== 'custom';
  $('#from').value = S.from; $('#to').value = S.to;
  $('#sort').value = S.sort;
}

function renderCats(cc) {
  const max = Math.max(1, ...Object.values(cc));
  $('#cats').innerHTML = CATS.map((c) => {
    const n = cc[c.key] || 0;
    const on = S.cat.includes(c.key);
    return `<button type="button" class="cat${n ? '' : ' zero'}" data-cat="${c.key}" aria-pressed="${on}">
      <span>${escHTML(c.label)}</span><span class="n">${n.toLocaleString('ko-KR')}</span>
      <span class="meter" aria-hidden="true"><i style="width:${(n / max) * 100}%"></i></span></button>`;
  }).join('');
  const box = $('#cats');
  const sel = box.querySelector('[aria-pressed="true"]');
  if (sel && box.scrollWidth > box.clientWidth) box.scrollLeft = Math.max(0, sel.offsetLeft - box.offsetLeft - 16);
}

function renderRadar(radar) {
  const cats = CATS.filter((c) => c.key !== TAX.fallback.key);
  const N = cats.length;
  const W = 300, H = 270, cx = 150, cy = 132, R = 88;
  const ang = (i) => -Math.PI / 2 + (i * 2 * Math.PI) / N;
  const pt = (i, r) => [cx + r * Math.cos(ang(i)), cy + r * Math.sin(ang(i))];
  const poly = (rs) => rs.map((r, i) => pt(i, r).map((v) => v.toFixed(1)).join(',')).join(' ');
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="분야별 수집 분포" style="--cx:${cx}px;--cy:${cy}px">`;
  for (const f of [0.25, 0.5, 0.75, 1]) s += `<polygon class="ring" points="${poly(cats.map(() => R * f))}"/>`;
  cats.forEach((_, i) => { const [x, y] = pt(i, R); s += `<line class="axis" x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}"/>`; });
  const types = TYPES.map(([t]) => t).filter((t) => S.tab === 'all' || S.tab === t);
  for (const t of types) {
    const vals = cats.map((c) => radar[t][c.key]);
    const mx = Math.max(...vals);
    if (!mx) continue;
    const rs = vals.map((v) => (v ? Math.max(0.08, Math.sqrt(v / mx)) : 0) * R);
    s += `<polygon class="shape" points="${poly(rs)}" style="fill:var(--t-${t});fill-opacity:.13;stroke:var(--t-${t})"/>`;
  }
  s += `<path class="sweep" d="M${cx} ${cy} L${cx} ${cy - R} A${R} ${R} 0 0 1 ${(cx + R * Math.sin(Math.PI / 5)).toFixed(1)} ${(cy - R * Math.cos(Math.PI / 5)).toFixed(1)} Z" fill="var(--ink)" opacity="0" style="fill-opacity:.07"/>`;
  cats.forEach((c, i) => {
    const [x, y] = pt(i, R + 15);
    const cos = Math.cos(ang(i));
    const anchor = cos > 0.25 ? 'start' : cos < -0.25 ? 'end' : 'middle';
    const dy = Math.sin(ang(i)) > 0.6 ? 10 : Math.sin(ang(i)) < -0.6 ? -2 : 4;
    const total = types.reduce((a, t) => a + radar[t][c.key], 0);
    const on = S.cat.includes(c.key);
    s += `<g class="ax${on ? ' on' : ''}" data-cat="${c.key}" tabindex="0" role="button" aria-pressed="${on}" aria-label="${escHTML(c.label)} ${total}건">
      <title>${escHTML(c.label)} — ${types.map((t) => `${TYPE_LABEL[t]} ${radar[t][c.key]}`).join(', ')}</title>
      <text x="${x.toFixed(1)}" y="${(y + dy).toFixed(1)}" text-anchor="${anchor}">${escHTML(c.short)}<tspan class="cnt" dx="3">${total}</tspan></text></g>`;
  });
  s += '</svg>';
  const fig = $('#radar');
  fig.innerHTML = s;
  if (firstPaint) { fig.classList.add('boot'); setTimeout(() => fig.classList.remove('boot'), 1300); }
  $('#legend').innerHTML = types.map((t) => `<span style="--c:var(--t-${t})"><i></i>${TYPE_LABEL[t]}</span>`).join('');
}

function renderTimeline(days) {
  const W = 280, H = 74, top = 6, base = 52, gap = 4;
  const bw = (W - gap * 13) / 14;
  const max = Math.max(1, ...days.map((d) => d.news + d.paper + d.patent));
  const t = today();
  const r = range();
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="최근 14일 일별 수집량">`;
  days.forEach((d, i) => {
    const x = i * (bw + gap);
    const on = S.period === 'custom' && r && d.day >= r[0] && d.day <= r[1];
    const tot = d.news + d.paper + d.patent;
    s += `<g class="day${d.day === t ? ' today' : ''}${on ? ' on' : ''}" data-day="${d.day}" role="button" tabindex="0"
      aria-label="${md(d.day)} ${tot}건"><title>${md(d.day)} — 뉴스 ${d.news}, 논문 ${d.paper}, 특허 ${d.patent}</title>
      <rect class="bg" x="${(x - 1).toFixed(1)}" y="0" width="${(bw + 2).toFixed(1)}" height="${H}" rx="4"/>`;
    let y = base;
    for (const [k] of TYPES) {
      if (S.tab !== 'all' && S.tab !== k) continue;
      const h = (d[k] / max) * (base - top);
      if (h > 0) { y -= h; s += `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(1, h).toFixed(1)}" rx="1.5" fill="var(--t-${k})"/>`; }
    }
    if (tot === 0) s += `<rect x="${x.toFixed(1)}" y="${base - 1}" width="${bw.toFixed(1)}" height="1" fill="var(--line)"/>`;
    s += `<text x="${(x + bw / 2).toFixed(1)}" y="${H - 6}" text-anchor="middle">${+d.day.slice(8)}</text></g>`;
  });
  $('#timeline').innerHTML = s + '</svg>';
}

function renderResultBar(n) {
  const pills = [];
  if (S.q.trim()) pills.push(`<button type="button" class="pill" data-clear="q">“${escHTML(S.q.trim())}” ${ICON_X}<span class="vh">검색어 지우기</span></button>`);
  for (const k of S.cat) if (CAT[k]) pills.push(`<button type="button" class="pill" data-clear-cat="${k}">${escHTML(CAT[k].label)} ${ICON_X}<span class="vh">분야 해제</span></button>`);
  if (S.period === 'custom' && (S.from || S.to)) pills.push(`<button type="button" class="pill" data-clear="period">${S.from ? md(S.from) : '처음'} ~ ${S.to ? md(S.to) : '오늘'} ${ICON_X}</button>`);
  const dirty = pills.length || S.tab !== 'all' || S.period !== DEFAULT_PERIOD || S.saved;
  $('#result-bar').innerHTML = `<span class="total">${n.toLocaleString('ko-KR')}건</span>${pills.join('')}
    ${dirty ? '<button type="button" class="linkish" data-reset>필터 초기화</button>' : ''}
    <button type="button" class="chip saved-toggle" data-saved aria-pressed="${S.saved}">저장한 항목 ${saved.size}</button>`;
}

function rowHTML(it, grouped) {
  const tags = it.cats.map((c) => CAT[c] ? `<button type="button" class="tag${S.cat.includes(c) ? ' on' : ''}" data-cat="${c}">${escHTML(CAT[c].label)}</button>` : '').join('');
  const foot = [tags];
  if (it.type === 'paper') {
    if (it.upvotes) foot.push(`<span class="up" title="Hugging Face 추천 수">추천 ${it.upvotes}</span>`);
    else if (it.hf) foot.push('<span class="up">HF 주목</span>');
    if (it.pdf) foot.push(`<a class="sub-link" href="${escHTML(it.pdf)}" target="_blank" rel="noopener">PDF</a>`);
    if (it.code) foot.push(`<a class="sub-link" href="${escHTML(it.code)}" target="_blank" rel="noopener">코드</a>`);
    if (it.arxiv && it.hf) foot.push(`<a class="sub-link" href="https://huggingface.co/papers/${escHTML(it.arxiv)}" target="_blank" rel="noopener">HF</a>`);
    if (it.authors) foot.push(`<span class="meta-txt">${highlight(it.authors, parsed)}</span>`);
  } else if (it.type === 'patent') {
    if (it.status) foot.push(`<span class="status-badge">${escHTML(it.status)}</span>`);
    if (it.authors) foot.push(`<span class="meta-txt">${highlight(it.authors, parsed)}</span>`);
    if (it.number) foot.push(`<span class="meta-txt" title="출원번호 ${escHTML(it.appno || '')}">${highlight(it.number, parsed)}</span>`);
    if (it.ipc && it.ipc.length) foot.push(`<span class="meta-txt" title="IPC">${escHTML(it.ipc.slice(0, 2).join(' '))}</span>`);
  } else if (it.also && it.also.length) {
    foot.push(`<details class="also"><summary>같은 소식 ${it.also.length}곳</summary><ul>${it.also.map((a) =>
      `<li><a href="${escHTML(a.url)}" target="_blank" rel="noopener">${escHTML(a.source || '다른 매체')}</a></li>`).join('')}</ul></details>`);
  }
  const sum = it.hf_sum || it.summary || '';
  const isNew = prevVisit && it._added > prevVisit;
  const on = saved.has(it.id);
  return `<article class="row" data-type="${it.type}" data-id="${it.id}">
    <div class="row-meta"><span class="kind">${TYPE_LABEL[it.type]}</span><span class="src">${escHTML(it.source || '')}</span>
      <time datetime="${escHTML(it.date)}">${when(it, grouped)}</time>${isNew ? '<span class="fresh">새 항목</span>' : ''}
      <button type="button" class="star" data-star="${it.id}" aria-pressed="${on}" aria-label="${on ? '저장 해제' : '저장'}">${ICON_STAR}</button></div>
    <h3><a href="${escHTML(it.url)}" target="_blank" rel="noopener" lang="${it.lang === 'en' ? 'en' : 'ko'}">${highlight(it.title, parsed)}</a></h3>
    ${sum ? `<p class="sum">${highlight(sum, parsed)}</p>` : ''}
    <div class="row-foot">${foot.join('')}</div></article>`;
}

function renderList(list) {
  const el = $('#list');
  if (!ITEMS.length) {
    el.innerHTML = `<div class="empty"><h3>아직 수집된 데이터가 없습니다</h3>
      <p>GitHub 저장소의 Actions 탭에서 <code>AI-Tech Radar 수집·배포</code> 워크플로를 한 번 실행하면 몇 분 뒤 채워집니다.</p>
      <p>로컬에서는 <code>python -m collector</code> 실행 후 <code>python -m http.server</code> 로 엽니다.</p></div>`;
    $('#more').innerHTML = '';
    return;
  }
  if (!list.length) {
    const wait = archive === 'loading' && needsArchive();
    el.innerHTML = `<div class="empty"><h3>${wait ? '이전 기록을 불러오는 중입니다' : '조건에 맞는 항목이 없습니다'}</h3>
      <p>${wait ? '잠시 후 결과가 나타납니다.' : '기간을 넓히거나 분야 선택을 풀어 보세요.'}</p>
      ${wait ? '' : '<button type="button" data-reset>필터 초기화</button>'}</div>`;
    $('#more').innerHTML = '';
    return;
  }
  const page = list.slice(0, shown);
  const grouped = S.sort === 'latest';
  let html = '';
  if (grouped) {
    let cur = null, buf = [];
    const flush = () => {
      if (!cur) return;
      const [a, b] = dayTitle(cur);
      const cnt = list.filter((x) => x._day === cur).length;
      html += `<h2 class="day-h">${a}<span class="sub">${b ? b + ' ' : ''}${cnt}건</span></h2><div class="sheet">${buf.join('')}</div>`;
    };
    for (const it of page) {
      if (it._day !== cur) { flush(); cur = it._day; buf = []; }
      buf.push(rowHTML(it, true));
    }
    flush();
  } else {
    html = `<div class="sheet">${page.map((it) => rowHTML(it, false)).join('')}</div>`;
  }
  el.innerHTML = html;
  const left = list.length - page.length;
  $('#more').innerHTML = left > 0
    ? `<button type="button" data-more>${Math.min(PAGE, left)}건 더 보기 <span style="color:var(--ink-3)">(남은 ${left.toLocaleString('ko-KR')}건)</span></button>`
    : (archive === 'loading' && needsArchive() ? '이전 기록을 불러오는 중…' : '');
  observeMore();
}

function renderMeta() {
  const g = Date.parse(META.generated || '');
  $('#updated').textContent = g ? `${md(dayOf(g))} ${fmtTime.format(g)} 갱신` : '';
  const note = $('#notice');
  if (META.demo) { note.hidden = false; note.textContent = '샘플 데이터로 만든 미리보기입니다. 실제 기사·논문·특허가 아니며 링크는 example.com 으로 연결됩니다.'; }
  const rows = (META.sources || []).map((s) => {
    const t = Date.parse(s.at || '');
    return `<tr><td>${escHTML(s.name)}</td><td>${TYPE_LABEL[s.type] || ''}</td>
      <td class="${s.ok ? 'ok' : 'bad'}">${s.ok ? '정상' : '실패'}</td><td>${s.ok ? `${s.count}건` : escHTML(s.error || '')}</td>
      <td>${t ? `${md(dayOf(t))} ${fmtTime.format(t)}` : ''}</td></tr>`;
  }).join('');
  const c = META.counts || {};
  $('#status-list').innerHTML = (META.sources || []).length
    ? `<p>누적 뉴스 ${(c.news || 0).toLocaleString('ko-KR')}건, 논문 ${(c.paper || 0).toLocaleString('ko-KR')}건, 특허 ${(c.patent || 0).toLocaleString('ko-KR')}건.
       보존 기간 뉴스 ${META.retention_days?.news ?? '-'}일, 논문 ${META.retention_days?.paper ?? '-'}일, 특허 ${META.retention_days?.patent ?? '-'}일.</p>
       <table><thead><tr><th>소스</th><th>유형</th><th>상태</th><th>결과</th><th>마지막 시도</th></tr></thead><tbody>${rows}</tbody></table>`
    : '<p>수집 기록이 없습니다.</p>';
}

function render({ keepPage = false } = {}) {
  if (!keepPage) shown = PAGE;
  const r = compute();
  renderTabs(r.typeCount);
  renderPeriods();
  renderCats(r.catCount);
  renderRadar(r.radar);
  renderTimeline(r.days);
  renderResultBar(r.list.length);
  renderList(r.list);
  firstPaint = false;
  writeHash();
  if (needsArchive() && archive === 'idle') loadArchive();
}

// ── 더 보기(스크롤 시 자동) ───────────────────────────────
let io;
function observeMore() {
  if (!('IntersectionObserver' in window)) return;
  io ||= new IntersectionObserver((ents) => {
    if (ents.some((e) => e.isIntersecting) && $('#more [data-more]')) { shown += PAGE; render({ keepPage: true }); }
  }, { rootMargin: '600px 0px' });
  io.disconnect();
  const b = $('#more [data-more]');
  if (b) io.observe(b);
}

async function loadArchive() {
  if (archive !== 'idle' || window.__ATR_DATA__) return;
  archive = 'loading';
  try {
    const doc = await getJSON(`data/items-archive.json?v=${encodeURIComponent(META.generated || '')}`);
    ingest(doc.items);
    archive = 'done';
  } catch { archive = 'error'; }
  render({ keepPage: true });
}

// ── 이벤트 ────────────────────────────────────────────────
function toggleCat(k) {
  S.cat = S.cat.includes(k) ? S.cat.filter((x) => x !== k) : [...S.cat, k];
  render();
}
function reset() {
  Object.assign(S, { tab: 'all', cat: [], period: DEFAULT_PERIOD, q: '', sort: 'latest', from: '', to: '', saved: false });
  $('#q').value = '';
  render();
}

function bind() {
  const q = $('#q');
  q.value = S.q;
  let timer;
  q.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => { S.q = q.value; render(); }, 140);
  });
  q.addEventListener('keydown', (e) => { if (e.key === 'Escape') { q.value = ''; S.q = ''; render(); } });
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && !/input|textarea|select/i.test(document.activeElement.tagName)) { e.preventDefault(); q.focus(); }
  });

  document.addEventListener('click', (e) => {
    const t = e.target.closest('button, g[role=button]');
    if (!t) return;
    if (t.dataset.tab) { S.tab = t.dataset.tab; render(); return; }
    if (t.dataset.period) {
      S.period = t.dataset.period;
      if (S.period === 'custom' && !S.from && !S.to) { S.from = addDays(today(), -13); S.to = today(); }
      if (S.period !== 'custom') { S.from = ''; S.to = ''; }
      render(); return;
    }
    if (t.dataset.cat) { toggleCat(t.dataset.cat); return; }
    if (t.dataset.day) {
      const d = t.dataset.day;
      if (S.period === 'custom' && S.from === d && S.to === d) { S.period = DEFAULT_PERIOD; S.from = S.to = ''; }
      else { S.period = 'custom'; S.from = S.to = d; }
      render(); return;
    }
    if (t.dataset.star) {
      const id = t.dataset.star;
      if (saved.has(id)) saved.delete(id); else saved.add(id);
      ls.set('atr.saved', [...saved]);
      const on = saved.has(id);
      t.setAttribute('aria-pressed', on); t.setAttribute('aria-label', on ? '저장 해제' : '저장');
      const st = $('[data-saved]'); if (st) st.textContent = `저장한 항목 ${saved.size}`;
      if (S.saved) render({ keepPage: true });
      return;
    }
    if (t.hasAttribute('data-saved')) { S.saved = !S.saved; render(); return; }
    if (t.hasAttribute('data-reset')) { reset(); return; }
    if (t.hasAttribute('data-more')) { shown += PAGE; render({ keepPage: true }); return; }
    if (t.dataset.clear === 'q') { S.q = ''; q.value = ''; render(); return; }
    if (t.dataset.clear === 'period') { S.period = DEFAULT_PERIOD; S.from = S.to = ''; render(); return; }
    if (t.dataset.clearCat) { toggleCat(t.dataset.clearCat); return; }
  });
  document.addEventListener('keydown', (e) => {
    const g = e.target.closest && e.target.closest('g[role=button]');
    if (g && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); g.dispatchEvent(new MouseEvent('click', { bubbles: true })); }
  });
  $('#sort').addEventListener('change', (e) => { S.sort = e.target.value; render(); });
  for (const id of ['from', 'to']) {
    $(`#${id}`).addEventListener('change', (e) => { S[id] = e.target.value; S.period = 'custom'; render(); });
  }
  window.addEventListener('hashchange', () => { readHash(); $('#q').value = S.q; render(); });
  $('#theme').addEventListener('click', () => {
    const root = document.documentElement;
    const dark = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    root.dataset.theme = dark ? 'light' : 'dark';
    try { localStorage.setItem('atr.theme', root.dataset.theme); } catch { /* 무시 */ }
  });
  if (matchMedia('(max-width: 960px)').matches) $('#viz').open = false;
  if (matchMedia('(max-width: 520px)').matches) q.placeholder = '검색어 — 예: 온디바이스, ㅅㅅㅎ';
}

// ── 시작 ──────────────────────────────────────────────────
async function boot() {
  readHash();
  bind();
  const inline = window.__ATR_DATA__;
  if (inline) {
    setTaxonomy(inline.taxonomy);
    META = inline.meta || {};
    ingest(inline.items);
    archive = 'done';
  } else {
    const [tax, meta] = await Promise.allSettled([getJSON('assets/taxonomy.json'), getJSON('data/meta.json')]);
    setTaxonomy(tax.status === 'fulfilled' ? tax.value : null);
    META = meta.status === 'fulfilled' ? meta.value : {};
    try {
      const doc = await getJSON(`data/items-recent.json?v=${encodeURIComponent(META.generated || '')}`);
      ingest(doc.items);
    } catch { /* 첫 배포 전 */ }
  }
  renderMeta();
  render();
  if (!inline) setTimeout(() => { if (archive === 'idle') loadArchive(); }, 1200);
}
boot();
