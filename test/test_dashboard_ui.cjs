const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { runInNewContext } = require('node:vm');
const { test } = require('node:test');
const assert = require('node:assert/strict');

const html = readFileSync(join(__dirname, '..', 'src', 'Inspector', 'Extensions', 'Dashboard.html'), 'utf8');
const script = html.split('<script>')[1].split('</script>')[0].replace(/\nrefresh\(\);\s*$/, '');

function fixture() {
  const elements = new Map();
  const classes = new Set();
  function element() {
    return {
      textContent: '', className: '', dataset: {}, children: [],
      append(child) { this.children.push(child); },
      replaceChildren(...children) { this.children = children; },
      setAttribute(name, value) { this[name] = value; }
    };
  }
  const context = {
    Intl, Date, Object, Math, AbortController,
    window: { location: { pathname: '/dashboard' } },
    document: {
      hidden: false,
      body: { classList: { add: name => classes.add(name), remove: name => classes.delete(name) } },
      getElementById(id) {
        if (!elements.has(id)) elements.set(id, element());
        return elements.get(id);
      },
      createElement: element,
      querySelectorAll() {
        return (elements.get('tasks')?.children ?? []).flatMap(row => row.children.filter(cell => cell.className === 'task-rate'));
      },
      addEventListener(name, callback) { this[name] = callback; }
    },
    setTimeout() { return 1; }, clearTimeout() {},
    fetch: async () => { throw new Error('offline'); }
  };
  runInNewContext(script, context);
  return { context, elements, classes, run: code => runInNewContext(code, context) };
}

function snapshot(time, success, failure = 0, instance = 'one') {
  return {
    instance, sampled_at: time, uptime: 60, running: true,
    tasks: { Task: {
      active: 2, success, failure, duration: (success + failure) * .25, oldest_active: 12,
      windows: {
        '1': { success, failure, duration: (success + failure) * .25, max_duration: .4 },
        '60': { success: 30, failure: 10, duration: 20, max_duration: 2 }
      }
    } }
  };
}

test('second and minute views use real server windows, not multiplied rates', () => {
  const { context, elements, run } = fixture();
  context.sample = snapshot(10, 5, 1);
  run('render(sample)');
  assert.equal(elements.get('rate').textContent, '6 /sec');
  const selector = context.document.getElementById('window');
  selector.value = '60';
  selector.onchange();
  assert.equal(elements.get('rate').textContent, '40 /min');
  assert.equal(elements.get('window-outcomes').textContent, '30 / 10');
  assert.equal(elements.get('failure-rate').textContent, '25%');
  assert.equal(elements.get('average').textContent, '500 ms');
  assert.equal(elements.get('maximum').textContent, '2,000 ms');
  assert.equal(elements.get('oldest').textContent, '12,000 ms');
  context.sample = snapshot(12, 0, 0, 'restarted');
  selector.value = '1';
  run('render(sample)');
  assert.equal(elements.get('rate').textContent, '0 /sec');
  assert.equal(elements.get('average').textContent, '--');
  assert.equal(elements.get('maximum').textContent, '--');
  assert.equal(elements.get('failure-rate').textContent, '--');
});

test('render displays rates, totals, cumulative milliseconds, empty state and safe task names', () => {
  const { context, elements, run } = fixture();
  context.sample = snapshot(1, 4);
  run('render(sample)');
  assert.equal(elements.get('rate').textContent, '4 /sec');
  assert.equal(elements.get('active').textContent, '2');
  assert.equal(elements.get('uptime').textContent, '00:01:00');
  assert.equal(elements.get('tasks').children[0].children[5].textContent, '250 ms');
  context.sample = snapshot(3, 10, 2);
  run('render(sample)');
  assert.equal(elements.get('rate').textContent, '12 /sec');
  assert.equal(elements.get('success').textContent, '10');
  assert.equal(elements.get('failure').textContent, '2');
  const malicious = '<img src=x onerror=alert(1)>';
  context.sample.tasks = { [malicious]: context.sample.tasks.Task };
  run('render(sample)');
  assert.equal(elements.get('tasks').children[0].children[0].textContent, malicious);
  context.sample.tasks = {};
  run('render(sample)');
  assert.equal(elements.get('empty').hidden, false);
  assert.equal(context.document.getElementById('tasks').children.length, 0);
});

test('aggregate windows weight averages by counts and take the maximum across tasks', () => {
  const { context, elements, run } = fixture();
  context.sample = snapshot(10, 2, 0);
  context.sample.tasks.Other = {
    active: 1, success: 1, failure: 0, duration: 2, oldest_active: 40,
    windows: {
      '1': { success: 1, failure: 0, duration: 2.5, max_duration: 2.5 },
      '60': { success: 1, failure: 0, duration: 2.5, max_duration: 2.5 }
    }
  };
  run('render(sample)');
  assert.equal(elements.get('rate').textContent, '3 /sec');
  assert.equal(elements.get('average').textContent, '1,000 ms');
  assert.equal(elements.get('maximum').textContent, '2,500 ms');
  assert.equal(elements.get('oldest').textContent, '40,000 ms');
});

test('polling marks disconnected totals stale, clears windows and recovers with server history', async () => {
  const { context, elements, classes, run } = fixture();
  let sample = snapshot(1, 1);
  context.fetch = async () => ({ ok: true, json: async () => sample });
  await run('refresh()');
  sample = snapshot(2, 5);
  await run('refresh()');
  assert.equal(elements.get('rate').textContent, '5 /sec');
  context.fetch = async () => { throw new Error('offline'); };
  await run('refresh()');
  assert.equal(classes.has('stale'), true);
  assert.equal(elements.get('notice').dataset.state, 'error');
  assert.match(elements.get('notice').textContent, /stale.*offline/);
  assert.equal(elements.get('rate').textContent, '--');
  assert.equal(elements.get('tasks').children[0].children[4].textContent, '--');
  context.fetch = async () => ({ ok: true, json: async () => snapshot(10, 25) });
  await run('refresh()');
  assert.equal(classes.has('stale'), false);
  assert.equal(elements.get('rate').textContent, '25 /sec');
});

test('polls never overlap, pause ignores in-flight results and hidden tabs do not fetch', async () => {
  const { context, elements, run } = fixture();
  let finish;
  let calls = 0;
  context.fetch = () => {
    calls++;
    return new Promise(resolve => { finish = resolve; });
  };
  const first = run('refresh()');
  await run('refresh()');
  assert.equal(calls, 1);
  elements.get('pause').onclick();
  finish({ ok: true, json: async () => snapshot(1, 1) });
  await first;
  assert.equal(context.document.getElementById('tasks').children.length, 0);
  assert.match(elements.get('notice').textContent, /Paused/);
  context.document.hidden = true;
  elements.get('pause').onclick();
  await run('refresh()');
  assert.equal(calls, 1);
});
