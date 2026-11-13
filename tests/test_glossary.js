/* test_glossary.js — checks the glossary data and matching logic.
 *
 *   node tests/test_glossary.js
 *
 * Runs without a browser by stubbing the handful of DOM calls glossary.js makes
 * at load time. The auto-linker itself is exercised against a tiny hand-written
 * DOM so we can prove it never corrupts markup, which is the one way a feature
 * like this could quietly ruin the app.
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log(`  PASS  ${name}`); }
  else { fail++; console.log(`  FAIL  ${name}  ${detail}`); }
};

/* ---- load glossary.js with a minimal document stub ---------------------- */
const src = fs.readFileSync(path.join(__dirname, '..', 'web', 'glossary.js'), 'utf8');
const sandbox = {
  console,
  document: { addEventListener() {}, createElement: () => ({ style: {}, classList: { contains: () => false } }), querySelector: () => null, body: { appendChild() {} } },
  window: { addEventListener() {} },
  NodeFilter: { SHOW_TEXT: 4, FILTER_REJECT: 2, FILTER_ACCEPT: 1 },
};
vm.createContext(sandbox);
// `const` at the top level of a script stays in lexical scope rather than
// landing on the global object, so export what we need explicitly.
vm.runInContext(src + '\n;globalThis.__GL = { GLOSSARY, GL_ENTRIES, GL_GROUPS, glossify, glRegex };', sandbox);
const { GLOSSARY, GL_ENTRIES, GL_GROUPS } = sandbox.__GL;

console.log('\n--- glossary data ---');

check('glossary has a useful number of terms', Object.keys(GLOSSARY).length >= 40,
  `${Object.keys(GLOSSARY).length} terms`);

const missingFields = Object.entries(GLOSSARY).filter(([, v]) => !v.t || !v.s || !v.d).map(([k]) => k);
check('every term has a title, one-liner and detail', missingFields.length === 0,
  missingFields.join(', '));

const tooLong = Object.entries(GLOSSARY).filter(([, v]) => v.s.length > 95).map(([k]) => k);
check('one-liners stay short enough to scan', tooLong.length === 0, tooLong.join(', '));

/* every grouped key exists, and every term is grouped exactly once */
const grouped = GL_GROUPS.flatMap(([, keys]) => keys);
const unknown = grouped.filter(k => !GLOSSARY[k]);
check('glossary tab references only real terms', unknown.length === 0, unknown.join(', '));

const ungrouped = Object.keys(GLOSSARY).filter(k => !grouped.includes(k));
check('every term appears in the reference tab', ungrouped.length === 0, ungrouped.join(', '));

const dupes = grouped.filter((k, i) => grouped.indexOf(k) !== i);
check('no term is listed in two groups', dupes.length === 0, dupes.join(', '));

/* no phrase should be claimed by two different terms */
const seen = new Map(), collisions = [];
for (const e of GL_ENTRIES) {
  const p = e.exact ? e.phrase : e.phrase.toLowerCase();
  if (seen.has(p) && seen.get(p) !== e.key) collisions.push(`${p}: ${seen.get(p)} vs ${e.key}`);
  seen.set(p, e.key);
}
check('no phrase is claimed by two terms', collisions.length === 0, collisions.join('; '));

check('entries are sorted longest-phrase-first so multi-word terms win',
  GL_ENTRIES.every((e, i) => i === 0 || GL_ENTRIES[i - 1].phrase.length >= e.phrase.length));

/* ---- matching behaviour ------------------------------------------------- */
console.log('\n--- matching behaviour ---');

const matches = (phrase, exact, text) => sandbox.__GL.glRegex(phrase, exact).test(text);

// Every phrase must match itself — catches regex-escaping mistakes in terms
// containing punctuation like "reward:risk" and "r:r".
const selfFail = GL_ENTRIES.filter(e => !matches(e.phrase, e.exact, `x ${e.phrase} y`));
check('every phrase matches itself (regex escaping is correct)', selfFail.length === 0,
  selfFail.map(e => e.phrase).join(', '));

check('whole-word only: "candle" does not match inside "candlestick-like"',
  !matches('candle', false, 'a candlesticklike thing'));
check('whole-word only: "atr" does not match inside "atrium"',
  !matches('atr', false, 'the atrium'));
check('case-insensitive by default: "RSI" matches "rsi"',
  matches('rsi', false, 'RSI is 40'));

// LONG / SHORT / FLAT must only link as uppercase UI labels, never as prose.
const exactKeys = ['long', 'short', 'flat'];
for (const k of exactKeys) {
  check(`"${k}" is case-sensitive, so prose is not underlined`, GLOSSARY[k].exact === true);
  const hasLowerPhrase = GL_ENTRIES.some(e => e.key === k && e.phrase === k);
  check(`lowercase "${k}" is not a linkable phrase`, !hasLowerPhrase);
  const upper = GL_ENTRIES.find(e => e.key === k && e.phrase === k.toUpperCase());
  check(`uppercase "${k.toUpperCase()}" is linkable`, !!upper);
  check(`"${k}" does not match ordinary prose`,
    !matches(k.toUpperCase(), true, `it took a ${k} time to finish`));
  check(`"${k.toUpperCase()}" matches the UI label`,
    matches(k.toUpperCase(), true, `state is ${k.toUpperCase()} right now`));
}

// Longer phrases must be tried before their shorter substrings.
const idx = p => GL_ENTRIES.findIndex(e => e.phrase === p);
check('"moving average" is tried before "sma"', idx('moving average') < idx('sma'));
check('"volume z-score" is tried before "volume"', idx('volume z-score') < idx('volume'));
check('"max drawdown" is tried before "drawdown"', idx('max drawdown') < idx('drawdown'));
check('"take profit" is tried before "stop"', idx('take profit') < idx('stop'));

/* ---- the auto-linker must not corrupt markup ---------------------------- */
console.log('\n--- auto-linker safety ---');

// Minimal DOM good enough for glossify(): text nodes, elements, TreeWalker.
class TextNode {
  constructor(v) { this.nodeType = 3; this.nodeValue = v; this.parentNode = null; }
  get textContent() { return this.nodeValue; }
}
class Frag {
  constructor() { this.children = []; }
  append(n) { this.children.push(n); }
}
class Elem {
  constructor(name, cls) {
    this.nodeType = 1; this.nodeName = name.toUpperCase();
    this.childNodes = []; this.parentNode = null;
    this.dataset = {}; this.className = cls || '';
    this.classList = { contains: c => (this.className || '').split(/\s+/).includes(c) };
  }
  append(n) { n.parentNode = this; this.childNodes.push(n); }
  set textContent(v) { this.childNodes = [new TextNode(v)]; }
  get textContent() { return this.childNodes.map(c => c.textContent).join(''); }
  get html() {
    return this.childNodes.map(c => c.nodeType === 3 ? c.nodeValue
      : `<${c.nodeName.toLowerCase()}${c.dataset.gl ? ` data-gl="${c.dataset.gl}"` : ''}>${c.html}</${c.nodeName.toLowerCase()}>`).join('');
  }
  replaceChild(frag, old) {
    const i = this.childNodes.indexOf(old);
    const kids = frag.children || [frag];
    kids.forEach(k => { k.parentNode = this; });
    this.childNodes.splice(i, 1, ...kids);
  }
}

sandbox.document.createElement = n => new Elem(n);
sandbox.document.createDocumentFragment = () => new Frag();
sandbox.document.createTextNode = v => new TextNode(v);
sandbox.document.createTreeWalker = (root, _what, filter) => {
  const nodes = [];
  (function walk(n) {
    for (const c of n.childNodes || []) {
      if (c.nodeType === 3) { if (filter.acceptNode(c) === 1) nodes.push(c); }
      else walk(c);
    }
  })(root);
  let i = -1;
  return { currentNode: null, nextNode() { i++; if (i >= nodes.length) return null; this.currentNode = nodes[i]; return nodes[i]; } };
};

const glossify = sandbox.__GL.glossify;

function build(name, text, cls) {
  const root = new Elem('div');
  const child = new Elem(name, cls);
  child.append(new TextNode(text));
  root.append(child);
  return root;
}

let root = build('p', 'The RSI is 40 and ADX is 22.');
glossify(root);
check('known terms get wrapped', root.html.includes('data-gl="rsi"') && root.html.includes('data-gl="adx"'),
  root.html);
check('surrounding text is preserved exactly',
  root.textContent === 'The RSI is 40 and ADX is 22.', root.textContent);

root = build('input', 'RSI in a form field');
glossify(root);
check('form inputs are never touched', !root.html.includes('data-gl'), root.html);

root = build('button', 'Buy on RSI');
glossify(root);
check('buttons are never touched', !root.html.includes('data-gl'), root.html);

root = build('span', 'drawdown here', 'gl');
glossify(root);
check('already-linked spans are not re-linked', !root.html.includes('data-gl'), root.html);

root = build('td', '$2,986.77 -4.2% 0.837024');
glossify(root);
check('pure numbers are left alone', root.textContent === '$2,986.77 -4.2% 0.837024');

root = build('p', 'RSI and RSI and RSI again');
glossify(root);
check('a term is linked at most once per render',
  (root.html.match(/data-gl="rsi"/g) || []).length === 1, root.html);

root = build('p', 'stop loss with a take profit and a trailing stop');
glossify(root);
check('overlapping terms do not mangle the text',
  root.textContent === 'stop loss with a take profit and a trailing stop', root.textContent);

root = build('p', 'nothing technical in this sentence at all');
glossify(root);
check('plain sentences are untouched when nothing matches',
  root.textContent === 'nothing technical in this sentence at all');

// Every key referenced by a wrapped span must resolve in GLOSSARY, or the
// popover would silently do nothing.
root = build('p', 'backtest overfitting slippage drawdown sharpe expectancy');
glossify(root);
const keys = [...root.html.matchAll(/data-gl="([^"]+)"/g)].map(m => m[1]);
check('every linked key resolves to a definition',
  keys.length > 0 && keys.every(k => !!GLOSSARY[k]), keys.join(','));

console.log(`\n${'='.repeat(46)}\n  ${pass} passed, ${fail} failed\n${'='.repeat(46)}\n`);
process.exit(fail ? 1 : 0);
