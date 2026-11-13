// 검색 엔진 테스트 — node --test tests/
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { buildLexicon, parseQuery, prepareHaystack, matchScore, highlight, chosung } from '../assets/search.js';

const tax = JSON.parse(readFileSync(new URL('../assets/taxonomy.json', import.meta.url), 'utf8'));
const lex = buildLexicon(tax.synonyms);
const item = (o) => prepareHaystack({ title: '', summary: '', ...o });
const score = (it, q) => matchScore(it, parseQuery(q, lex));

const en = item({ title: 'Nvidia unveils HBM-based inference chip', summary: 'The company said the chain of supply…' });
const ko = item({ title: '생성형 AI로 휴머노이드 로봇 학습 데이터 만든다', summary: '피지컬 AI 실증', source: 'AI타임스' });
const pat = item({ title: '인공 신경망 양자화 방법', authors: '테스트전자주식회사', number: '10-2026-0099001', ipc: ['G06N3/08'] });

test('한글 질의가 영문 항목을 찾는다(동의어)', () => {
  assert.ok(score(en, '엔비디아') > 0);
  assert.ok(score(en, '반도체') > 0);
  assert.equal(score(ko, '엔비디아'), 0);
});

test('띄어쓰기를 무시한다', () => {
  assert.ok(score(ko, '생성형AI') > 0);
  assert.ok(score(ko, '휴머 노이드') > 0);
  assert.ok(score(ko, '로봇학습') > 0);
});

test('초성 검색', () => {
  assert.equal(chosung('휴머노이드 로봇'), 'ㅎㅁㄴㅇㄷㄹㅂ');
  assert.ok(score(ko, 'ㅎㅁㄴㅇㄷ') > 0);
  assert.equal(score(en, 'ㅎㅁㄴㅇㄷ'), 0);
});

test('짧은 영문은 단어 경계로만 맞춘다', () => {
  const x = item({ title: 'Supply chain update', summary: 'said' });
  assert.equal(score(x, 'ai'), 0);            // chain·said 안의 ai 는 무시
  assert.ok(score(ko, 'ai') > 0);             // '생성형 AI' 는 일치
});

test('제외어·구문·OR', () => {
  assert.equal(score(en, 'chip -nvidia'), 0);
  assert.ok(score(en, '"inference chip"') > 0);
  assert.equal(score(en, '"chip inference"'), 0);
  assert.ok(score(en, 'zzz|hbm') > 0);
});

test('조사가 붙어도 동의어를 찾는다', () => {
  assert.ok(score(en, '엔비디아의') > 0);
});

test('출원인·번호로 찾는다', () => {
  assert.ok(score(pat, '테스트전자') > 0);
  assert.ok(score(pat, '1020260099001') > 0);
  assert.ok(score(pat, 'G06N3') > 0);
});

test('제목 일치가 더 높은 점수', () => {
  assert.ok(score(ko, '휴머노이드') > score(ko, 'AI타임스'));
});

test('하이라이트는 안전하게 이스케이프한다', () => {
  const p = parseQuery('생성형ai', lex);
  assert.equal(highlight('<b>생성형 AI</b>', p), '&lt;b&gt;<mark>생성형 AI</mark>&lt;/b&gt;');
  assert.equal(highlight('A & B', parseQuery('amp', lex)), 'A &amp; B');
});
