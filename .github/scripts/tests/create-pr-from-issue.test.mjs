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

const footer = '- Closes #12\n- Changes: issues/task/12/CHANGELOG.md';

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
  'IR.md': `# PR 제목\n\n## 변경 내용\n\n간결한 변경 설명\n\n## 검증\n\n테스트 통과\n\n${footer}`,
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

test('buildPullRequest uses the authored PR document instead of copying work records', () => {
  const result = buildPullRequest({
    template,
    documents,
    issueDirectory: 'issues/task/12',
    owner: 'example',
    repo: 'project',
    sha: 'abc123',
  });
  assert.equal(result.title, 'PR 제목');
  assert.equal(result.body, '## 변경 내용\n\n간결한 변경 설명\n\n## 검증\n\n테스트 통과\n\n- Closes #12\n- Changes: issues/task/12/CHANGELOG.md');
});

test('buildPullRequest requires IR.md even when the previous PR.md exists', () => {
  assert.throws(() => buildPullRequest({
    documents: { 'PR.md': '# 이전 제목\n\n이전 본문' },
    issueDirectory: 'issues/task/12',
    owner: 'example',
    repo: 'project',
    sha: 'abc123',
  }), /PR body is missing or empty: issues\/task\/12\/IR\.md/);
});

test('buildPullRequest uses the issue directory in the final changelog path', () => {
  const result = buildPullRequest({
    template,
    documents: { ...documents, 'IR.md': documents['IR.md'].replace(footer, '- Closes #34\n- Changes: issues/feature/34/CHANGELOG.md') },
    issueDirectory: 'issues/feature/34',
    owner: 'example',
    repo: 'project',
    sha: 'abc123',
  });
  assert.match(result.body, /- Closes #34\n- Changes: issues\/feature\/34\/CHANGELOG\.md$/);
});

test('buildPullRequest accepts multiple closing keywords and checks only the last nonblank line', () => {
  for (const closings of [
    '- Closes #12, Closes #13, Closes #14',
    '- Closes #13\n- Closes #12\n- Closes #14',
  ]) {
    const markdown = `# PR 제목\n\n본문\n\n${closings}\n- Changes: issues/task/12/CHANGELOG.md\n\n`;
    const result = buildPullRequest({
      documents: { 'IR.md': markdown },
      issueDirectory: 'issues/task/12',
      owner: 'example',
      repo: 'project',
      sha: 'abc123',
    });
    assert.equal(result.body, markdown.slice(markdown.indexOf('\n') + 1).trim());
  }
});

test('buildPullRequest preserves literal content in the PR document', () => {
  const literal = "Literal $& $$ $' $`";
  const result = buildPullRequest({
    template,
    documents: { ...documents, 'IR.md': `${documents['IR.md'].slice(0, -footer.length)}${literal}\n\n${footer}` },
    issueDirectory: 'issues/task/12',
    owner: 'example',
    repo: 'project',
    sha: 'abc123',
  });
  assert.ok(result.body.includes(literal));
});

test('buildPullRequest resolves document links while preserving code and external URLs', () => {
  const changed = {
    ...documents,
    'IR.md': [
      '# PR 제목',
      '[API](../../../docs/API.md#usage)',
      '![Image](./images/example.png)',
      '[Root](/README.md)',
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
      '[Task](./tasks/789.md)',
      footer,
    ].join('\n'),
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
    '[Anchor](#검증)',
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

test('buildPullRequest expands reference links in the PR document', () => {
  const result = buildPullRequest({
    template,
    documents: {
      ...documents,
      'IR.md': [
        '# Requirements',
        '## 목적',
        '[Record][ID] and [ID][] and [ID]',
        '## References',
        '[id]: ./docs/record.md "Record title"',
        footer,
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
      'IR.md': `# Changes\n[Outside](../../../../outside.md)\n${footer}`,
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

for (const markdown of ['## 제목\n본문', '#   \n본문', `# ${'x'.repeat(257)}\n본문`]) {
  test(`buildPullRequest rejects an invalid PR title: ${markdown.length}`, () => {
    assert.throws(() => buildPullRequest({
      template,
      documents: { ...documents, 'IR.md': markdown },
      issue: sourceIssue,
      issueDirectory: 'issues/task/12',
      owner: 'example',
      repo: 'project',
      sha: 'abc123',
    }), /PR title must be a non-empty first-line heading/);
  });
}

test('buildPullRequest accepts a 256-character title and rejects a missing body', () => {
  const options = {
    documents: { 'IR.md': `# ${'x'.repeat(256)}\r\n\r\n본문\r\n\r\n${footer}` },
    issueDirectory: 'issues/task/12',
    owner: 'example',
    repo: 'project',
    sha: 'abc123',
  };
  assert.equal(buildPullRequest(options).title, 'x'.repeat(256));
  assert.throws(
    () => buildPullRequest({ ...options, documents: { 'IR.md': '# 제목\n \n' } }),
    /PR body is missing or empty/,
  );
});

test('buildPullRequest accepts the exact body limit and rejects an oversized PR document', () => {
  const options = {
    template,
    documents: { 'IR.md': `# 제목\n\nx\n\n${footer}` },
    issue: sourceIssue,
    issueDirectory: 'issues/task/12',
    owner: 'example',
    repo: 'project',
    sha: 'abc123',
  };
  const content = 'x'.repeat(65536 - buildPullRequest(options).body.length + 1);
  const atLimit = buildPullRequest({ ...options, documents: { 'IR.md': `# 제목\n\n${content}\n\n${footer}` } });
  assert.equal(atLimit.body.length, 65536);
  assert.ok(atLimit.body.includes(content));
  assert.match(atLimit.body, /- Closes #12\n- Changes: issues\/task\/12\/CHANGELOG\.md$/);
  assert.throws(
    () => buildPullRequest({ ...options, documents: { 'IR.md': `# 제목\n\n${content}x\n\n${footer}` } }),
    /PR body exceeds the 65536-character limit/,
  );
});

for (const file of ['IR.md', 'CHANGELOG.md']) {
  test(`createPullRequest propagates non-missing read errors for ${file}`, async () => {
    const rootDirectory = await makeIssueDirectory();
    const path = join(rootDirectory, 'issues', 'task', '12', file);
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

for (const content of [null, '', ' \n\t']) {
  test(`createPullRequest rejects a ${content === null ? 'missing' : 'empty'} changelog before creating a PR`, async () => {
    const rootDirectory = await makeIssueDirectory();
    const requests = [];
    try {
      const changelog = join(rootDirectory, 'issues', 'task', '12', 'CHANGELOG.md');
      if (content === null) {
        await rm(changelog);
      } else {
        await writeFile(changelog, content);
      }
      await assert.rejects(createPullRequest({
        owner: 'example', repo: 'project', branch: 'task/12', base: 'master',
        sha: 'abc123', token: 'test-token', rootDirectory,
        fetchImpl: async (url, options) => {
          requests.push({ url, options });
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
      }), /Changelog is missing or empty: issues\/task\/12\/CHANGELOG\.md/);
      assert.equal(requests.some(({ options }) => options.method === 'POST'), false);
    } finally {
      await rm(rootDirectory, { recursive: true, force: true });
    }
  });
}

test('createPullRequest accepts a PR document and changelog without other issue documents or a template', async () => {
  const rootDirectory = await makeIssueDirectory();
  let payload;
  try {
    await rm(join(rootDirectory, '.github', 'PULL_REQUEST_TEMPLATE.md'));
    for (const fileName of Object.keys(documents)) {
      if (!['CHANGELOG.md', 'IR.md'].includes(fileName)) {
        await rm(join(rootDirectory, 'issues', 'task', '12', fileName));
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
    assert.equal(payload.title, 'PR 제목');
    assert.match(payload.body, /- Closes #12\n- Changes: issues\/task\/12\/CHANGELOG\.md$/);
  } finally {
    await rm(rootDirectory, { recursive: true, force: true });
  }
});

test('createPullRequest updates agent PRs using all pages of changed files', async () => {
  const rootDirectory = await makeIssueDirectory();
  try {
    for (const branch of ['copilot/example', 'codex/example']) {
      const requests = [];
      const result = await createPullRequest({
        owner: 'example', repo: 'project', branch, base: 'master',
        sha: 'abc123', token: 'test-token', rootDirectory,
        fetchImpl: async (url, options) => {
          requests.push({ url, options });
          if (url.includes('/pulls?')) {
            return jsonResponse([{ number: 8, node_id: pullRequestNodeId, head: { sha: 'abc123' } }]);
          }
          if (url.includes('/pulls/8/files?') && url.endsWith('page=1')) {
            return jsonResponse(Array.from({ length: 100 }, (_, index) => ({
              filename: `src/file${index}.js`, status: 'modified',
            })));
          }
          if (url.includes('/pulls/8/files?') && url.endsWith('page=2')) {
            return jsonResponse([
              { filename: 'issues/task/99/IR.md', status: 'removed' },
              { filename: 'issues/task/12/IR.md', status: 'added' },
            ]);
          }
          if (url.endsWith('/pulls/8') && options.method === 'PATCH') return jsonResponse({});
          throw new Error(`Unexpected request: ${url}`);
        },
      });
      assert.deepEqual(result, { status: 'already-open', number: 8 });
      assert.equal(requests.length, 4);
      assert.deepEqual(JSON.parse(requests[3].options.body), {
        title: 'PR 제목',
        body: `## 변경 내용\n\n간결한 변경 설명\n\n## 검증\n\n테스트 통과\n\n${footer}`,
      });
    }
  } finally {
    await rm(rootDirectory, { recursive: true, force: true });
  }
});

test('createPullRequest rejects missing, ambiguous, or incomplete agent PR file lists', async () => {
  const rootDirectory = await makeIssueDirectory();
  try {
    for (const [files, error] of [
      [[], /Expected exactly one changed issue IR\.md, found 0/],
      [[
        { filename: 'issues/task/12/IR.md', status: 'modified' },
        { filename: 'issues/feature/13/IR.md', status: 'added' },
      ], /Expected exactly one changed issue IR\.md, found 2/],
      [Array.from({ length: 100 }, (_, index) => ({
        filename: `src/file${index}.js`, status: 'modified',
      })), /3000-file limit/],
    ]) {
      const requests = [];
      await assert.rejects(createPullRequest({
        owner: 'example', repo: 'project', branch: 'copilot/example', base: 'master',
        sha: 'abc123', token: 'test-token', rootDirectory,
        fetchImpl: async (url, options) => {
          requests.push({ url, options });
          if (url.includes('/pulls?')) {
            return jsonResponse([{ number: 8, node_id: pullRequestNodeId, head: { sha: 'abc123' } }]);
          }
          if (url.includes('/pulls/8/files?')) return jsonResponse(files);
          throw new Error(`Unexpected request: ${url}`);
        },
      }), error);
      assert.equal(requests.some(({ options }) => ['POST', 'PATCH'].includes(options.method)), false);
    }
  } finally {
    await rm(rootDirectory, { recursive: true, force: true });
  }
});

test('createPullRequest skips agent pushes without an open PR or with an outdated SHA', async () => {
  for (const [pulls, status] of [
    [[], 'no-open-agent-pull-request'],
    [[{ number: 8, node_id: pullRequestNodeId, head: { sha: 'newer' } }], 'stale-agent-push'],
  ]) {
    const result = await createPullRequest({
      owner: 'example', repo: 'project', branch: 'copilot/example', base: 'master',
      sha: 'abc123', token: 'test-token',
      fetchImpl: async (url) => {
        if (url.includes('/pulls?')) return jsonResponse(pulls);
        throw new Error(`Unexpected request: ${url}`);
      },
    });
    assert.deepEqual(result, { status });
  }
});

test('createPullRequest updates an existing open PR without creating another', async () => {
  const rootDirectory = await makeIssueDirectory();
  const requests = [];
  try {
    await writeFile(join(rootDirectory, 'issues', 'task', '12', 'README.md'), '# 최신 작업 제목');
    await writeFile(join(rootDirectory, 'issues', 'task', '12', 'CHANGELOG.md'), '# 변경 로그\n\n- 최신 변경');
    await writeFile(join(rootDirectory, 'issues', 'task', '12', 'IR.md'), `# 최신 PR 제목\n\n## 변경 내용\n\n최신 PR 본문\n\n${footer}`);
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
          return jsonResponse([{ number: 8, node_id: pullRequestNodeId, title: '기존 제목', body: '수동 작성' }]);
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
        if (url.endsWith('/pulls/8')) {
          return jsonResponse({});
        }
        if (url.endsWith('/issues/8')) {
          return jsonResponse({ milestone: { number: 3 } });
        }
        return jsonResponse([{ name: 'task' }, { name: 'automation' }]);
      },
    });

    assert.deepEqual(result, { status: 'already-open', number: 8 });
    assert.equal(requests.length, 7);
    assert.match(requests[0].url, /head=example%3Atask%2F12/);
    assert.match(requests[1].url, /\/issues\/12$/);
    assert.match(requests[2].url, /\/pulls\/8$/);
    assert.equal(requests[2].options.method, 'PATCH');
    const updated = JSON.parse(requests[2].options.body);
    assert.deepEqual(Object.keys(updated).sort(), ['body', 'title']);
    assert.equal(updated.title, '최신 PR 제목');
    assert.doesNotMatch(updated.body, /최신 PR 제목/);
    assert.match(updated.body, /최신 PR 본문/);
    assert.doesNotMatch(updated.body, /최신 변경/);
    assert.match(updated.body, /- Closes #12\n- Changes: issues\/task\/12\/CHANGELOG\.md$/);
    assert.doesNotMatch(updated.body, /수동 작성/);
    assert.match(requests[3].url, /\/issues\/8\/labels$/);
    assert.deepEqual(JSON.parse(requests[3].options.body), {
      labels: ['task', 'automation'],
    });
    assert.match(requests[4].url, /\/issues\/8\/assignees$/);
    assert.deepEqual(JSON.parse(requests[4].options.body), { assignees: ['owner'] });
    assert.match(requests[5].url, /\/issues\/8$/);
    assert.equal(requests[5].options.method, 'PATCH');
    assert.deepEqual(JSON.parse(requests[5].options.body), { milestone: 3 });
    assert.match(requests[6].url, /\/graphql$/);
    assert.match(JSON.parse(requests[6].options.body).query, /addCloseIssueReferences/);
    assert.deepEqual(JSON.parse(requests[6].options.body).variables, {
      input: { issueId: issueNodeId, pullRequestIds: [pullRequestNodeId] },
    });
    assert.equal(requests.some(({ url }) => url.endsWith('/requested_reviewers')), false);
    assert.equal(requests.some(({ url, options }) => url.endsWith('/pulls') && options.method === 'POST'), false);
  } finally {
    await rm(rootDirectory, { recursive: true, force: true });
  }
});

for (const existing of [false, true]) {
  for (const [description, content, error] of [
    ['missing', null, /PR body is missing or empty/],
    ['blank', ' \n', /PR body is missing or empty/],
    ['missing title', '## 제목\n본문', /PR title must be a non-empty first-line heading/],
    ['missing body', '# 제목\n', /PR body is missing or empty/],
    ['missing footer', '# 제목\n\n본문', /IR document must end with the changelog entry/],
    ['wrong changelog', '# 제목\n\n본문\n\n- Closes #12\n- Changes: issues/task/13/CHANGELOG.md', /IR document must end with the changelog entry/],
  ]) {
    test(`createPullRequest rejects a PR document with ${description} before ${existing ? 'updating' : 'creating'} a PR`, async () => {
      const rootDirectory = await makeIssueDirectory();
      const requests = [];
      try {
        const path = join(rootDirectory, 'issues', 'task', '12', 'IR.md');
        if (content === null) {
          await rm(path);
        } else {
          await writeFile(path, content);
        }
        await assert.rejects(createPullRequest({
          owner: 'example', repo: 'project', branch: 'task/12', base: 'master',
          sha: 'abc123', token: 'test-token', rootDirectory,
          fetchImpl: async (url, options) => {
            requests.push({ url, options });
            if (url.includes('/pulls?')) {
              return jsonResponse(existing ? [{ number: 8, node_id: pullRequestNodeId }] : []);
            }
            if (url.includes('/compare/')) return comparisonResponse(1);
            if (url.endsWith('/git/commits/abc123')) {
              return jsonResponse({ tree: { sha: 'head-tree' } });
            }
            if (url.endsWith('/issues/12')) {
              return jsonResponse({ ...sourceIssue, node_id: issueNodeId, labels: [], assignees: [], milestone: null });
            }
            throw new Error(`Unexpected request: ${url}`);
          },
        }), error);
        assert.equal(requests.some(({ options }) => ['POST', 'PATCH'].includes(options.method)), false);
      } finally {
        await rm(rootDirectory, { recursive: true, force: true });
      }
    });
  }
}

for (const content of [null, ' \n']) {
  test(`createPullRequest rejects ${content === null ? 'a missing' : 'an empty'} changelog before updating an existing PR`, async () => {
    const rootDirectory = await makeIssueDirectory();
    const requests = [];
    try {
      const path = join(rootDirectory, 'issues', 'task', '12', 'CHANGELOG.md');
      if (content === null) {
        await rm(path);
      } else {
        await writeFile(path, content);
      }
      await assert.rejects(createPullRequest({
        owner: 'example', repo: 'project', branch: 'task/12', base: 'master',
        sha: 'abc123', token: 'test-token', rootDirectory,
        fetchImpl: async (url, options) => {
          requests.push({ url, options });
          if (url.includes('/pulls?')) {
            return jsonResponse([{ number: 8, node_id: pullRequestNodeId }]);
          }
          if (url.endsWith('/issues/12')) {
            return jsonResponse({ node_id: issueNodeId, labels: [], assignees: [], milestone: null });
          }
          throw new Error(`Unexpected request: ${url}`);
        },
      }), /Changelog is missing or empty: issues\/task\/12\/CHANGELOG\.md/);
      assert.equal(requests.some(({ options }) => ['POST', 'PATCH'].includes(options.method)), false);
    } finally {
      await rm(rootDirectory, { recursive: true, force: true });
    }
  });
}

test('createPullRequest propagates errors when updating an existing PR', async () => {
  const rootDirectory = await makeIssueDirectory();
  const requests = [];
  try {
    await assert.rejects(createPullRequest({
      owner: 'example', repo: 'project', branch: 'task/12', base: 'master',
      sha: 'abc123', token: 'test-token', rootDirectory,
      fetchImpl: async (url, options) => {
        requests.push({ url, options });
        if (url.includes('/pulls?')) {
          return jsonResponse([{ number: 8, node_id: pullRequestNodeId }]);
        }
        if (url.endsWith('/issues/12')) {
          return jsonResponse({ node_id: issueNodeId, labels: [], assignees: [], milestone: null });
        }
        if (url.endsWith('/pulls/8')) {
          return jsonResponse({ message: 'Resource not accessible by integration' }, 403);
        }
        throw new Error(`Unexpected request: ${url}`);
      },
    }), /GitHub API request failed \(403\): Resource not accessible by integration/);
    assert.equal(requests.length, 3);
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
    assert.equal(payload.draft, true);
    assert.equal(payload.title, 'PR 제목');
    assert.match(payload.body, /간결한 변경 설명/);
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
            if (url.endsWith('/pulls/15')) {
              return jsonResponse({});
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
