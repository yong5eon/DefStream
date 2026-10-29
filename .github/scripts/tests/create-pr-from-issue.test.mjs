import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  buildPullRequest,
  createPullRequest,
  parseIssueBranch,
} from '../create-pr-from-issue.mjs';

const template = [
  '## 변경 내용',
  '<!-- 무엇을 왜 변경했는지 간단히 요약해 주세요. -->',
  '## 변경 유형',
  '- [ ] 버그 수정 및 일반 변경, 핫픽스 처리',
  '- [ ] 기능 추가',
  '- [ ] 기타',
  '## 검증',
  '<!-- 실행한 테스트와 결과를 작성해 주세요. 테스트를 실행하지 않았다면 사유를 적어 주세요. -->',
].join('\n\n');

const documents = {
  'README.md': '# 작업 기록 제목',
  'REQUIREMENTS.md': '# 요구사항\n\n## 목적\n요청된 동작을 구현한다.',
  'CHANGELOG.md': '# 변경 로그\n\n- 사용자가 새 동작을 이용할 수 있다.',
  'IMPLEMENTS.md': [
    '# 구현 결과',
    '',
    '## 구현 내용',
    '- 자동 PR 생성을 추가했다.',
    '',
    '## 검증 및 제한',
    '- 단위 테스트를 실행했다.',
  ].join('\n'),
  'TASKS.md': '# 작업 기록\n\n## 최신 검증\n\n- 자동화 테스트 4개 통과.',
};
const issueNodeId = 'I_issue_12';
const pullRequestNodeId = 'PR_15';

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), { status });
}

function graphqlLinkResponse() {
  return jsonResponse({
    data: { addCloseIssueReferences: { issue: { id: issueNodeId } } },
  });
}

function comparisonResponse(aheadBy) {
  return jsonResponse({
    ahead_by: aheadBy,
    files: [{ filename: 'src/change.py' }],
    base_commit: { commit: { tree: { sha: 'base-tree' } } },
  });
}

async function makeIssueDirectory() {
  const rootDirectory = await mkdtemp(join(tmpdir(), 'create-pr-'));
  await mkdir(join(rootDirectory, '.github'), { recursive: true });
  await mkdir(join(rootDirectory, 'issues', 'task', '12'), { recursive: true });
  await writeFile(join(rootDirectory, '.github', 'PULL_REQUEST_TEMPLATE.md'), template);
  for (const [fileName, content] of Object.entries(documents)) {
    await writeFile(join(rootDirectory, 'issues', 'task', '12', fileName), content);
  }
  return rootDirectory;
}

test('parseIssueBranch maps supported branch names to issue directories', () => {
  assert.equal(parseIssueBranch('task/12'), 'issues/task/12');
  assert.equal(parseIssueBranch('feature/PROJ-4'), 'issues/feature/PROJ-4');
  assert.throws(() => parseIssueBranch('topic/12'), /does not identify/);
  assert.throws(() => parseIssueBranch('task/12/unsafe'), /does not identify/);
});

test('buildPullRequest fills the repository template only from issue documents', () => {
  const result = buildPullRequest({
    template,
    documents,
    issueDirectory: 'issues/task/12',
    owner: 'example',
    repo: 'project',
    sha: 'abc123',
  });

  assert.equal(result.title, '작업 기록 제목');
  assert.match(result.body, /요청된 동작을 구현한다/);
  assert.match(result.body, /사용자가 새 동작을 이용할 수 있다/);
  assert.match(result.body, /자동 PR 생성을 추가했다/);
  assert.match(result.body, /자동화 테스트 4개 통과/);
  assert.match(result.body, /blob\/abc123\/issues\/task\/12\/REQUIREMENTS\.md/);
  assert.match(result.body, /- \[X\] 기타/);
  assert.match(result.body, /- \[ \] 기능 추가/);
  assert.match(result.body, /Closes #12$/);
  assert.doesNotMatch(result.body, /<!--/);
  assert.doesNotMatch(result.body, /commit message/i);
});

test('buildPullRequest preserves replacement patterns verbatim in every document', () => {
  const literal = "Literal $& $$ $' $`";
  const changed = Object.fromEntries(
    Object.entries(documents).map(([name, text]) => [name, `${text}\n\n${literal}`]),
  );
  const result = buildPullRequest({
    template,
    documents: changed,
    issueDirectory: 'issues/task/12',
    owner: 'example',
    repo: 'project',
    sha: 'abc123',
  });
  assert.equal(result.body.split(literal).length - 1, 5);
  assert.doesNotMatch(result.body, /<!--/);
});

test('buildPullRequest resolves document links while preserving code and external URLs', () => {
  const changed = {
    ...documents,
    'REQUIREMENTS.md': `${documents['REQUIREMENTS.md']}\n[API](../../../docs/API.md#usage)`,
    'CHANGELOG.md': `${documents['CHANGELOG.md']}\n![Image](./images/example.png)\n[Root](/README.md)`,
    'IMPLEMENTS.md': documents['IMPLEMENTS.md'].replace(
      '- 자동 PR 생성을 추가했다.',
      [
        '[Record](./implements/123.md)',
        '[Space](<./docs/a b.md> "Details")',
        '[Encoded](./docs/a%20b.md?raw=1#part)',
        '[Parentheses](./docs/example(v1).md)',
        '[Anchor](#검증)',
        '[Web](https://example.com/a)',
        '[Mail](mailto:owner@example.com)',
        '[Protocol](//example.com/a)',
        '`[Inline code](./unchanged.md)`',
        '```markdown',
        '[Fenced example](./unchanged.md)',
        '```',
        '[Reference][record]',
        '[record]: ./implements/456.md "Reference title"',
      ].join('\n'),
    ),
    'TASKS.md': `${documents['TASKS.md']}\n[Task](./tasks/789.md)`,
  };
  const result = buildPullRequest({
    template,
    documents: changed,
    issueDirectory: 'issues/task/12',
    owner: 'example',
    repo: 'project',
    sha: 'abc123',
  });
  const url = 'https://github.com/example/project/blob/abc123/';
  for (const fragment of [
    `[API](${url}docs/API.md#usage)`,
    `![Image](${url}issues/task/12/images/example.png)`,
    `[Root](${url}README.md)`,
    `[Record](${url}issues/task/12/implements/123.md)`,
    `[Space](<${url}issues/task/12/docs/a%20b.md> "Details")`,
    `[Encoded](${url}issues/task/12/docs/a%20b.md?raw=1#part)`,
    `[Parentheses](${url}issues/task/12/docs/example(v1).md)`,
    `[Anchor](${url}issues/task/12/IMPLEMENTS.md#검증)`,
    `[Task](${url}issues/task/12/tasks/789.md)`,
    `${url}issues/task/12/implements/456.md`,
    '[Web](https://example.com/a)',
    '[Mail](mailto:owner@example.com)',
    '[Protocol](//example.com/a)',
    '`[Inline code](./unchanged.md)`',
    '```markdown\n[Fenced example](./unchanged.md)\n```',
  ]) {
    assert.ok(result.body.includes(fragment), `Missing fragment: ${fragment}`);
  }
});

test('buildPullRequest expands references defined outside the extracted section', () => {
  const result = buildPullRequest({
    template,
    documents: {
      ...documents,
      'REQUIREMENTS.md': [
        '# Requirements',
        '## 목적',
        '[Record][ID] and [ID][] and [ID]',
        '## References',
        '[id]: ./docs/record.md "Record title"',
      ].join('\n'),
    },
    issueDirectory: 'issues/task/12',
    owner: 'example',
    repo: 'project',
    sha: 'abc123',
  });
  const destination = '(https://github.com/example/project/blob/abc123/issues/task/12/docs/record.md "Record title")';
  assert.ok(result.body.includes(`[Record]${destination} and [ID]${destination} and [ID]${destination}`));
});

test('buildPullRequest rejects relative links that escape the repository', () => {
  assert.throws(() => buildPullRequest({
    template,
    documents: {
      ...documents,
      'CHANGELOG.md': '# Changes\n[Outside](../../../../outside.md)',
    },
    issueDirectory: 'issues/task/12',
    owner: 'example',
    repo: 'project',
    sha: 'abc123',
  }), /Markdown link escapes the repository/);
});

const sourceIssue = {
  title: 'Source issue title',
  body: 'Source issue description',
};

for (const scenario of [
  { name: 'arbitrary headings', documents: {
    'README.md': '# Existing document title',
    'REQUIREMENTS.md': '# Requirements\n\n## 1. 목적 및 범위\nActual requirements',
    'IMPLEMENTS.md': '# Results\n\n### Changes\nActual implementation',
  } },
  { name: 'only task records', documents: { 'TASKS.md': 'Actual task verification' } },
  { name: 'no documents', documents: {} },
  { name: 'empty documents', documents: { 'README.md': '', 'REQUIREMENTS.md': ' \n' } },
  { name: 'README without a heading', documents: { 'README.md': 'Actual overview' } },
  { name: 'overlong README title', documents: { 'README.md': `# ${'x'.repeat(257)}` } },
]) {
  test(`buildPullRequest accepts ${scenario.name}`, () => {
    const result = buildPullRequest({
      template,
      documents: scenario.documents,
      issue: sourceIssue,
      issueDirectory: 'issues/task/12',
      owner: 'example',
      repo: 'project',
      sha: 'abc123',
    });
    assert.equal(result.title, scenario.name === 'arbitrary headings'
      ? 'Existing document title' : sourceIssue.title);
    for (const content of Object.values(scenario.documents).filter((value) => value.trim())) {
      assert.ok(result.body.includes(content));
    }
    if (!Object.values(scenario.documents).some((value) => value.trim())) {
      assert.ok(result.body.includes(sourceIssue.body));
    }
    assert.match(result.body, /https:\/\/github.com\/example\/project\/issues\/12/);
    assert.match(result.body, /Closes #12$/);
  });
}

for (const changedTemplate of ['', '## Custom template\nKeep this text']) {
  test(`buildPullRequest accepts a template without fixed placeholders: ${changedTemplate.length}`, () => {
    const result = buildPullRequest({
      template: changedTemplate,
      documents,
      issue: sourceIssue,
      issueDirectory: 'issues/task/12',
      owner: 'example',
      repo: 'project',
      sha: 'abc123',
    });
    assert.ok(result.body.includes(changedTemplate));
    assert.match(result.body, /사용자가 새 동작/);
    assert.match(result.body, /자동화 테스트 4개 통과/);
  });
}

test('buildPullRequest links oversized documents instead of exceeding the PR body limit', () => {
  const result = buildPullRequest({
    template,
    documents: { 'TASKS.md': 'x'.repeat(70000) },
    issue: sourceIssue,
    issueDirectory: 'issues/task/12',
    owner: 'example',
    repo: 'project',
    sha: 'abc123',
  });
  assert.ok(result.body.length < 65536);
  assert.match(result.body, /blob\/abc123\/issues\/task\/12\/TASKS.md/);
});

test('buildPullRequest preserves template placeholders embedded in source documents', () => {
  const content = `${template}\n\nLiteral $& $$ $' $\``;
  const result = buildPullRequest({
    template,
    documents: { 'README.md': '# Title', 'TASKS.md': content },
    issue: sourceIssue,
    issueDirectory: 'issues/task/12',
    owner: 'example',
    repo: 'project',
    sha: 'abc123',
  });
  assert.ok(result.body.includes(content));
});

test('buildPullRequest preserves content at the exact body limit and links it above the limit', () => {
  const options = {
    template,
    documents: { 'TASKS.md': 'x' },
    issue: sourceIssue,
    issueDirectory: 'issues/task/12',
    owner: 'example',
    repo: 'project',
    sha: 'abc123',
  };
  const content = 'x'.repeat(65536 - buildPullRequest(options).body.length + 1);
  const atLimit = buildPullRequest({ ...options, documents: { 'TASKS.md': content } });
  assert.equal(atLimit.body.length, 65536);
  assert.ok(atLimit.body.includes(content));
  const aboveLimit = buildPullRequest({ ...options, documents: { 'TASKS.md': `${content}x` } });
  assert.ok(aboveLimit.body.length < 65536);
  assert.ok(!aboveLimit.body.includes(content));
  assert.match(aboveLimit.body, /blob\/abc123\/issues\/task\/12\/TASKS.md/);
});

test('buildPullRequest links an oversized template while retaining the issue and document links', () => {
  const result = buildPullRequest({
    template: 'x'.repeat(70000),
    documents,
    issue: sourceIssue,
    issueDirectory: 'issues/task/12',
    owner: 'example',
    repo: 'project',
    sha: 'abc123',
  });
  assert.ok(result.body.length < 65536);
  assert.match(result.body, /blob\/abc123\/\.github\/PULL_REQUEST_TEMPLATE.md/);
  assert.match(result.body, /blob\/abc123\/issues\/task\/12\/TASKS.md/);
  assert.match(result.body, /Closes #12$/);
});

for (const body of [null, 'x'.repeat(70000)]) {
  test(`buildPullRequest accepts source issues with ${body === null ? 'no' : 'oversized'} body`, () => {
    const result = buildPullRequest({
      template,
      documents: {},
      issue: { ...sourceIssue, body },
      issueDirectory: 'issues/task/12',
      owner: 'example',
      repo: 'project',
      sha: 'abc123',
    });
    assert.equal(result.title, sourceIssue.title);
    assert.ok(result.body.length < 65536);
    assert.match(result.body, /https:\/\/github.com\/example\/project\/issues\/12/);
    assert.match(result.body, /Closes #12$/);
  });
}

for (const file of ['TASKS.md', 'PULL_REQUEST_TEMPLATE.md']) {
  test(`createPullRequest propagates non-missing read errors for ${file}`, async () => {
    const rootDirectory = await makeIssueDirectory();
    const path = file === 'TASKS.md'
      ? join(rootDirectory, 'issues', 'task', '12', file)
      : join(rootDirectory, '.github', file);
    try {
      await rm(path);
      await mkdir(path);
      await assert.rejects(createPullRequest({
        owner: 'example', repo: 'project', branch: 'task/12', base: 'master',
        sha: 'abc123', token: 'test-token', rootDirectory,
        fetchImpl: async (url) => {
          if (url.includes('/pulls?')) return jsonResponse([]);
          if (url.includes('/compare/')) return comparisonResponse(1);
          if (url.endsWith('/git/commits/abc123')) {
            return jsonResponse({ tree: { sha: 'head-tree' } });
          }
          if (url.endsWith('/issues/12')) {
            return jsonResponse({
              ...sourceIssue, labels: [], assignees: [], milestone: null, node_id: issueNodeId,
            });
          }
          throw new Error(`Unexpected request: ${url}`);
        },
      }), { code: 'EISDIR' });
    } finally {
      await rm(rootDirectory, { recursive: true, force: true });
    }
  });
}

for (const scenario of [
  { name: 'missing documents and template', remove: true },
  { name: 'empty documents', remove: false },
]) {
  test(`createPullRequest creates a PR from the source issue with ${scenario.name}`, async () => {
    const rootDirectory = await makeIssueDirectory();
    let payload;
    try {
      if (scenario.remove) {
        await rm(join(rootDirectory, 'issues', 'task', '12'), { recursive: true });
        await rm(join(rootDirectory, '.github', 'PULL_REQUEST_TEMPLATE.md'));
      } else {
        for (const fileName of Object.keys(documents)) {
          await writeFile(join(rootDirectory, 'issues', 'task', '12', fileName), '');
        }
      }
      const result = await createPullRequest({
        owner: 'example', repo: 'project', branch: 'task/12', base: 'master',
        sha: 'abc123', token: 'test-token', rootDirectory,
        fetchImpl: async (url, options) => {
          if (url.includes('/pulls?')) return jsonResponse([]);
          if (url.includes('/compare/')) return comparisonResponse(1);
          if (url.endsWith('/git/commits/abc123')) {
            return jsonResponse({ tree: { sha: 'head-tree' } });
          }
          if (url.endsWith('/issues/12')) {
            return jsonResponse({
              ...sourceIssue, labels: [], assignees: [], milestone: null, node_id: issueNodeId,
            });
          }
          if (url.endsWith('/pulls')) {
            payload = JSON.parse(options.body);
            return jsonResponse({
              number: 15, node_id: pullRequestNodeId,
              html_url: 'https://github.com/example/project/pull/15',
            }, 201);
          }
          if (url.endsWith('/graphql')) return graphqlLinkResponse();
          throw new Error(`Unexpected request: ${url}`);
        },
      });
      assert.equal(result.status, 'created');
      assert.equal(payload.title, sourceIssue.title);
      assert.ok(payload.body.includes(sourceIssue.body));
      assert.match(payload.body, /Closes #12$/);
    } finally {
      await rm(rootDirectory, { recursive: true, force: true });
    }
  });
}

test('createPullRequest skips an existing open PR without creating another', async () => {
  const rootDirectory = await makeIssueDirectory();
  const requests = [];
  try {
    const result = await createPullRequest({
      owner: 'example',
      repo: 'project',
      branch: 'task/12',
      base: 'master',
      sha: 'abc123',
      token: 'test-token',
      rootDirectory,
      fetchImpl: async (url, options) => {
        requests.push({ url, options });
        if (url.includes('/pulls?')) {
          return jsonResponse([{ number: 8, node_id: pullRequestNodeId }]);
        }
        if (url.endsWith('/issues/12')) {
          return jsonResponse({
            node_id: issueNodeId,
            milestone: { number: 3 },
            labels: [{ name: 'task' }, { name: 'automation' }],
            assignees: [{ login: 'owner' }],
          });
        }
        if (url.endsWith('/graphql')) {
          return graphqlLinkResponse();
        }
        if (url.endsWith('/issues/8')) {
          return jsonResponse({ milestone: { number: 3 } });
        }
        return jsonResponse([{ name: 'task' }, { name: 'automation' }]);
      },
    });

    assert.deepEqual(result, { status: 'already-open', number: 8 });
    assert.equal(requests.length, 6);
    assert.match(requests[0].url, /head=example%3Atask%2F12/);
    assert.match(requests[1].url, /\/issues\/12$/);
    assert.match(requests[2].url, /\/issues\/8\/labels$/);
    assert.deepEqual(JSON.parse(requests[2].options.body), {
      labels: ['task', 'automation'],
    });
    assert.match(requests[3].url, /\/issues\/8\/assignees$/);
    assert.deepEqual(JSON.parse(requests[3].options.body), { assignees: ['owner'] });
    assert.match(requests[4].url, /\/issues\/8$/);
    assert.equal(requests[4].options.method, 'PATCH');
    assert.deepEqual(JSON.parse(requests[4].options.body), { milestone: 3 });
    assert.match(requests[5].url, /\/graphql$/);
    assert.match(JSON.parse(requests[5].options.body).query, /addCloseIssueReferences/);
    assert.deepEqual(JSON.parse(requests[5].options.body).variables, {
      input: { issueId: issueNodeId, pullRequestIds: [pullRequestNodeId] },
    });
    assert.equal(requests.some(({ url }) => url.endsWith('/requested_reviewers')), false);
  } finally {
    await rm(rootDirectory, { recursive: true, force: true });
  }
});

test('createPullRequest fails when GitHub cannot link the existing PR to its issue', async () => {
  const rootDirectory = await makeIssueDirectory();
  try {
    await assert.rejects(createPullRequest({
      owner: 'example',
      repo: 'project',
      branch: 'task/12',
      base: 'master',
      sha: 'abc123',
      token: 'test-token',
      rootDirectory,
      fetchImpl: async (url) => {
        if (url.includes('/pulls?')) {
          return jsonResponse([{ number: 8, node_id: pullRequestNodeId }]);
        }
        if (url.endsWith('/issues/12')) {
          return jsonResponse({
            node_id: issueNodeId,
            milestone: null,
            labels: [{ name: 'task' }],
            assignees: [],
          });
        }
        if (url.endsWith('/graphql')) {
          return jsonResponse({ errors: [{ message: 'Resource not accessible by integration' }] });
        }
        return jsonResponse([{ name: 'task' }]);
      },
    }), /GitHub GraphQL API request failed \(200\): Resource not accessible by integration/);
  } finally {
    await rm(rootDirectory, { recursive: true, force: true });
  }
});

test('createPullRequest creates a new PR after a merged PR when branch has new commits', async () => {
  const rootDirectory = await makeIssueDirectory();
  const requests = [];
  try {
    const result = await createPullRequest({
      owner: 'example',
      repo: 'project',
      branch: 'task/12',
      base: 'master',
      sha: 'abc123',
      token: 'test-token',
      rootDirectory,
      fetchImpl: async (url, options) => {
        requests.push({ url, options });
        if (url.includes('/pulls?')) {
          return jsonResponse([]);
        }
        if (url.includes('/compare/')) {
          return comparisonResponse(2);
        }
        if (url.endsWith('/git/commits/abc123')) {
          return jsonResponse({ tree: { sha: 'head-tree' } });
        }
        if (url.endsWith('/issues/12')) {
          return jsonResponse({
            node_id: issueNodeId,
            milestone: { number: 3 },
            labels: [{ name: 'task' }],
            assignees: [{ login: 'owner' }, { login: 'maintainer' }],
          });
        }
        if (url.endsWith('/pulls')) {
          return jsonResponse({
            number: 15,
            node_id: pullRequestNodeId,
            html_url: 'https://github.com/example/project/pull/15',
          }, 201);
        }
        if (url.endsWith('/graphql')) {
          return graphqlLinkResponse();
        }
        if (url.endsWith('/issues/15')) {
          return jsonResponse({ milestone: { number: 3 } });
        }
        return jsonResponse([{ name: 'task' }]);
      },
    });

    assert.deepEqual(result, {
      status: 'created',
      number: 15,
      url: 'https://github.com/example/project/pull/15',
    });
    const createRequest = requests[4];
    const payload = JSON.parse(createRequest.options.body);
    assert.equal(payload.head, 'task/12');
    assert.equal(payload.base, 'master');
    assert.equal(payload.title, '작업 기록 제목');
    assert.match(payload.body, /사용자가 새 동작을 이용할 수 있다/);
    assert.equal(requests.length, 9);
    assert.match(requests[1].url, /\/compare\/master\.\.\.abc123$/);
    assert.match(requests[2].url, /\/git\/commits\/abc123$/);
    assert.match(requests[4].url, /\/pulls$/);
    assert.match(requests[5].url, /\/issues\/15\/labels$/);
    assert.deepEqual(JSON.parse(requests[5].options.body), { labels: ['task'] });
    assert.match(requests[6].url, /\/issues\/15\/assignees$/);
    assert.deepEqual(JSON.parse(requests[6].options.body), {
      assignees: ['owner', 'maintainer'],
    });
    assert.match(requests[7].url, /\/issues\/15$/);
    assert.equal(requests[7].options.method, 'PATCH');
    assert.deepEqual(JSON.parse(requests[7].options.body), { milestone: 3 });
    assert.match(requests[8].url, /\/graphql$/);
    assert.deepEqual(JSON.parse(requests[8].options.body).variables, {
      input: { issueId: issueNodeId, pullRequestIds: [pullRequestNodeId] },
    });
    assert.equal(requests.some(({ url }) => url.endsWith('/requested_reviewers')), false);
  } finally {
    await rm(rootDirectory, { recursive: true, force: true });
  }
});

test('createPullRequest fails when source issue labels cannot be applied', async () => {
  const rootDirectory = await makeIssueDirectory();
  try {
    await assert.rejects(createPullRequest({
      owner: 'example',
      repo: 'project',
      branch: 'task/12',
      base: 'master',
      sha: 'abc123',
      token: 'test-token',
      rootDirectory,
      fetchImpl: async (url, options) => {
        if (url.includes('/pulls?')) {
          return jsonResponse([]);
        }
        if (url.includes('/compare/')) {
          return comparisonResponse(1);
        }
        if (url.endsWith('/git/commits/abc123')) {
          return jsonResponse({ tree: { sha: 'head-tree' } });
        }
        if (url.endsWith('/issues/12')) {
          return jsonResponse({
            node_id: issueNodeId,
            milestone: null,
            labels: [{ name: 'task' }],
            assignees: [],
          });
        }
        if (url.endsWith('/pulls')) {
          return jsonResponse({
            number: 16,
            node_id: pullRequestNodeId,
            html_url: 'https://github.com/example/project/pull/16',
          }, 201);
        }
        return jsonResponse({ message: 'Resource not accessible by integration' }, 403);
      },
    }), /GitHub API request failed \(403\)/);
  } finally {
    await rm(rootDirectory, { recursive: true, force: true });
  }
});

test('createPullRequest skips assignee updates when the source issue has no assignees', async () => {
  const rootDirectory = await makeIssueDirectory();
  const requests = [];
  try {
    const result = await createPullRequest({
      owner: 'example',
      repo: 'project',
      branch: 'task/12',
      base: 'master',
      sha: 'abc123',
      token: 'test-token',
      rootDirectory,
      fetchImpl: async (url, options) => {
        requests.push({ url, options });
        if (url.includes('/pulls?')) {
          return jsonResponse([]);
        }
        if (url.includes('/compare/')) {
          return comparisonResponse(1);
        }
        if (url.endsWith('/git/commits/abc123')) {
          return jsonResponse({ tree: { sha: 'head-tree' } });
        }
        if (url.endsWith('/issues/12')) {
          return jsonResponse({
            node_id: issueNodeId,
            milestone: null,
            labels: [{ name: 'task' }],
            assignees: [],
          });
        }
        if (url.endsWith('/pulls')) {
          return jsonResponse({
            number: 17,
            node_id: pullRequestNodeId,
            html_url: 'https://github.com/example/project/pull/17',
          }, 201);
        }
        if (url.endsWith('/graphql')) {
          return graphqlLinkResponse();
        }
        return jsonResponse([{ name: 'task' }]);
      },
    });

    assert.deepEqual(result, {
      status: 'created',
      number: 17,
      url: 'https://github.com/example/project/pull/17',
    });
    assert.equal(requests.length, 7);
    assert.equal(requests.some(({ url }) => url.endsWith('/issues/17/assignees')), false);
  } finally {
    await rm(rootDirectory, { recursive: true, force: true });
  }
});

test('createPullRequest fails when source issue assignees cannot be applied', async () => {
  const rootDirectory = await makeIssueDirectory();
  try {
    await assert.rejects(createPullRequest({
      owner: 'example',
      repo: 'project',
      branch: 'task/12',
      base: 'master',
      sha: 'abc123',
      token: 'test-token',
      rootDirectory,
      fetchImpl: async (url) => {
        if (url.includes('/pulls?')) {
          return jsonResponse([]);
        }
        if (url.includes('/compare/')) {
          return comparisonResponse(1);
        }
        if (url.endsWith('/git/commits/abc123')) {
          return jsonResponse({ tree: { sha: 'head-tree' } });
        }
        if (url.endsWith('/issues/12')) {
          return jsonResponse({
            node_id: issueNodeId,
            milestone: null,
            labels: [{ name: 'task' }],
            assignees: [{ login: 'owner' }],
          });
        }
        if (url.endsWith('/pulls')) {
          return jsonResponse({
            number: 18,
            node_id: pullRequestNodeId,
            html_url: 'https://github.com/example/project/pull/18',
          }, 201);
        }
        if (url.endsWith('/issues/18/assignees')) {
          return jsonResponse({ message: 'Resource not accessible by integration' }, 403);
        }
        return jsonResponse([{ name: 'task' }]);
      },
    }), /GitHub API request failed \(403\)/);
  } finally {
    await rm(rootDirectory, { recursive: true, force: true });
  }
});

for (const existing of [false, true]) {
  for (const scenario of [
    { name: 'replaces a different PR milestone', source: { number: 3 }, applied: { number: 3 } },
    { name: 'accepts an already matching milestone', source: { number: 2 }, applied: { number: 2 } },
    { name: 'preserves PR milestone when source is unset', source: null },
    { name: 'rejects a missing source milestone', source: undefined, error: /invalid milestone/ },
    { name: 'rejects a malformed source milestone', source: {}, error: /invalid milestone/ },
    { name: 'rejects a string milestone number', source: { number: '3' }, error: /invalid milestone/ },
    { name: 'rejects a nonpositive milestone number', source: { number: 0 }, error: /invalid milestone/ },
    {
      name: 'propagates milestone API failures',
      source: { number: 3 },
      status: 403,
      error: /GitHub API request failed \(403\)/,
    },
    {
      name: 'rejects a milestone that was not applied',
      source: { number: 3 },
      applied: { number: 2 },
      error: /did not confirm milestone 3 for PR #15/,
    },
    {
      name: 'rejects a missing milestone in the update response',
      source: { number: 3 },
      error: /did not confirm milestone 3 for PR #15/,
    },
  ]) {
    test(`createPullRequest ${existing ? 'existing' : 'new'} PR ${scenario.name}`, async () => {
      const rootDirectory = await makeIssueDirectory();
      const requests = [];
      let currentMilestone = { number: 2 };
      try {
        const operation = createPullRequest({
          owner: 'example',
          repo: 'project',
          branch: 'task/12',
          base: 'master',
          sha: 'abc123',
          token: 'test-token',
          rootDirectory,
          fetchImpl: async (url, options) => {
            requests.push({ url, options });
            if (url.includes('/pulls?')) {
              return jsonResponse(existing
                ? [{ number: 15, node_id: pullRequestNodeId, milestone: currentMilestone }]
                : []);
            }
            if (url.includes('/compare/')) {
              return comparisonResponse(1);
            }
            if (url.endsWith('/git/commits/abc123')) {
              return jsonResponse({ tree: { sha: 'head-tree' } });
            }
            if (url.endsWith('/issues/12')) {
              return jsonResponse({
                node_id: issueNodeId,
                labels: [],
                assignees: [],
                milestone: scenario.source,
              });
            }
            if (url.endsWith('/pulls')) {
              return jsonResponse({
                number: 15,
                node_id: pullRequestNodeId,
                html_url: 'https://github.com/example/project/pull/15',
              }, 201);
            }
            if (url.endsWith('/issues/15')) {
              assert.equal(options.method, 'PATCH');
              assert.deepEqual(JSON.parse(options.body), { milestone: scenario.source.number });
              if (scenario.status) {
                return jsonResponse({ message: 'Resource not accessible by integration' }, scenario.status);
              }
              currentMilestone = scenario.applied;
              return jsonResponse({ milestone: currentMilestone });
            }
            if (url.endsWith('/graphql')) {
              return graphqlLinkResponse();
            }
            throw new Error(`Unexpected request: ${url}`);
          },
        });
        if (scenario.error) {
          await assert.rejects(operation, scenario.error);
        } else {
          const result = await operation;
          assert.equal(result.status, existing ? 'already-open' : 'created');
          assert.deepEqual(currentMilestone, scenario.source ?? { number: 2 });
        }
        const milestoneRequests = requests.filter(({ url }) => url.endsWith('/issues/15'));
        const validSource = Number.isSafeInteger(scenario.source?.number)
          && scenario.source.number > 0;
        assert.equal(milestoneRequests.length, validSource ? 1 : 0);
        if (scenario.error) {
          assert.equal(requests.some(({ url }) => url.endsWith('/graphql')), false);
          if (!validSource) {
            assert.equal(requests.some(({ options }) => options.method === 'POST'), false);
          }
        }
      } finally {
        await rm(rootDirectory, { recursive: true, force: true });
      }
    });
  }
}

for (const scenario of [
  { name: 'missing base tree', base: {} },
  { name: 'empty base tree', base: { commit: { tree: { sha: '' } } } },
  { name: 'missing head tree', head: {} },
  { name: 'empty head tree', head: { tree: { sha: '' } } },
  { name: 'head lookup API failure', status: 403, error: /GitHub API request failed \(403\)/ },
]) {
  test(`createPullRequest rejects ${scenario.name} before creating a PR`, async () => {
    const requests = [];
    await assert.rejects(createPullRequest({
      owner: 'example',
      repo: 'project',
      branch: 'task/12',
      base: 'master',
      sha: 'abc123',
      token: 'test-token',
      fetchImpl: async (url, options) => {
        requests.push({ url, options });
        if (url.includes('/pulls?')) {
          return jsonResponse([]);
        }
        if (url.includes('/compare/')) {
          return jsonResponse({
            ahead_by: 3,
            files: [{ filename: 'src/change.py' }],
            base_commit: scenario.base ?? { commit: { tree: { sha: 'base-tree' } } },
          });
        }
        if (url.endsWith('/git/commits/abc123')) {
          return scenario.status
            ? jsonResponse({ message: 'Resource not accessible by integration' }, scenario.status)
            : jsonResponse(scenario.head ?? { tree: { sha: 'head-tree' } });
        }
        throw new Error(`Unexpected request: ${url}`);
      },
    }), scenario.error ?? /did not return the base and head commit tree SHAs/);
    assert.equal(requests.length, 3);
    assert.equal(requests.some(({ options }) => options.method === 'POST'), false);
  });
}

test('createPullRequest skips the default branch without API calls', async () => {
  const result = await createPullRequest({
    owner: 'example',
    repo: 'project',
    branch: 'master',
    base: 'master',
    sha: 'abc123',
    token: 'test-token',
    fetchImpl: async (url) => {
      throw new Error(`Unexpected request: ${url}`);
    },
  });
  assert.deepEqual(result, { status: 'default-branch' });
});

test('createPullRequest skips when there are no commits ahead of base', async () => {
  const rootDirectory = await makeIssueDirectory();
  let requestCount = 0;
  try {
    const result = await createPullRequest({
      owner: 'example',
      repo: 'project',
      branch: 'task/12',
      base: 'master',
      sha: 'abc123',
      token: 'test-token',
      rootDirectory,
      fetchImpl: async (url) => {
        requestCount += 1;
        return url.includes('/pulls?')
          ? jsonResponse([])
          : jsonResponse({ ahead_by: 0, files: [] });
      },
    });

    assert.deepEqual(result, { status: 'no-changes' });
    assert.equal(requestCount, 2);
  } finally {
    await rm(rootDirectory, { recursive: true, force: true });
  }
});

test('createPullRequest skips a squash-merged branch when its tree matches base', async () => {
  const rootDirectory = await makeIssueDirectory();
  let requestCount = 0;
  try {
    const result = await createPullRequest({
      owner: 'example',
      repo: 'project',
      branch: 'task/12',
      base: 'master',
      sha: 'abc123',
      token: 'test-token',
      rootDirectory,
      fetchImpl: async (url) => {
        requestCount += 1;
        return url.includes('/pulls?')
          ? jsonResponse([])
          : url.includes('/compare/')
            ? jsonResponse({
              ahead_by: 3,
              files: [{ filename: 'src/already-merged.py' }],
              base_commit: { commit: { tree: { sha: 'same-tree' } } },
            })
            : jsonResponse({ tree: { sha: 'same-tree' } });
      },
    });

    assert.deepEqual(result, { status: 'no-changes' });
    assert.equal(requestCount, 3);
  } finally {
    await rm(rootDirectory, { recursive: true, force: true });
  }
});
