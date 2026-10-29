import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import { readFile } from 'node:fs/promises';
import {
  buildIssueBody,
  buildIssuePayload,
  isSubmittedReviewEvent,
  parseCopilotResponse,
  processReview,
  runCopilot,
} from '../create-issues-from-reviews.mjs';

process.env.GITHUB_TOKEN ??= 'test-token';

const review = {
  id: 321,
  body: 'The transaction can be lost when commit fails.',
  html_url: 'https://github.com/example/project/pull/9#pullrequestreview-321',
  submitted_at: '2026-10-26T17:00:00Z',
  user: { login: 'copilot-pull-request-reviewer[bot]' },
};
const comment = {
  id: 654,
  pull_request_review_id: 321,
  body: 'The timeout is ignored when `wait()` is called.',
  html_url: 'https://github.com/example/project/pull/9#discussion_r654',
  path: 'src/Connection.py',
  line: 42,
  user: { login: 'copilot-pull-request-reviewer' },
};
const event = {
  action: 'submitted',
  review: {
    state: 'commented',
    author_association: 'NONE',
    user: { login: 'copilot-pull-request-reviewer[bot]' },
  },
  pull_request: {
    number: 9,
    html_url: 'https://github.com/example/project/pull/9',
    head: { ref: 'bug/3' },
  },
};
const finding = {
  comment_id: comment.id,
  title: '대기 시간 초과 설정 반영',
  problem: '`wait()` 호출 시 대기 시간 초과가 무시됩니다.',
  action: '`wait()`가 설정된 제한 시간을 적용하도록 수정해야 합니다.',
  label: 'bug',
  form_fields: {
    version: null,
    expected: null,
    actual: null,
    reproduction: null,
    environment: null,
    additional: null,
  },
};

function jsonResponse(data, status = 200, headers = {}) {
  return new Response(JSON.stringify(data), { status, headers });
}

function graphqlThreadsResponse(threads, pageInfo = { hasNextPage: false, endCursor: null }) {
  return jsonResponse({
    data: {
      repository: {
        pullRequest: {
          reviewThreads: {
            nodes: threads.map(({ id = 'thread-id', isResolved, commentIds, commentsPageInfo }) => ({
              id,
              isResolved,
              comments: {
                nodes: commentIds.map((fullDatabaseId) => ({
                  fullDatabaseId: String(fullDatabaseId),
                })),
                pageInfo: commentsPageInfo ?? { hasNextPage: false, endCursor: null },
              },
            })),
            pageInfo,
          },
        },
      },
    },
  });
}

test('accepts submitted reviews regardless of reviewer association or review state', () => {
  for (const state of ['commented', 'approved', 'changes_requested']) {
    for (const author_association of ['OWNER', 'COLLABORATOR', 'MEMBER', 'NONE']) {
      assert.equal(isSubmittedReviewEvent({
        ...event,
        review: { ...event.review, state, author_association },
      }), true);
    }
  }
  assert.equal(isSubmittedReviewEvent({ ...event, action: 'edited' }), false);
  assert.equal(isSubmittedReviewEvent({ ...event, action: 'dismissed' }), false);
  assert.equal(isSubmittedReviewEvent({ ...event, review: undefined }), false);
  assert.equal(isSubmittedReviewEvent({ ...event, pull_request: undefined }), false);
  assert.equal(isSubmittedReviewEvent(undefined), false);
});

test('workflow handles submitted reviews without PR approval or reviewer association filters', async () => {
  const workflow = await readFile(
    new URL('../../workflows/create-issues-from-reviews.yml', import.meta.url),
    'utf8',
  );
  assert.match(workflow, /pull_request_review:\s+types: \[submitted\]/);
  assert.match(workflow, /^name: Create issues from PR reviews$/m);
  assert.doesNotMatch(workflow, /github\.event\.review\.(state|author_association)/);
});

test('parses one Korean finding per valid Copilot comment', () => {
  const findings = parseCopilotResponse(JSON.stringify({ findings: [finding] }), [comment]);
  assert.deepEqual(findings, [{
    commentId: comment.id,
    title: finding.title,
    problem: finding.problem,
    action: finding.action,
    label: 'bug',
    formFields: {
      version: null,
      expected: null,
      actual: null,
      reproduction: null,
      environment: null,
      additional: null,
    },
  }]);
  assert.deepEqual(parseCopilotResponse('{"findings":[]}', [comment]), []);
});

test('rejects invalid output, unknown or duplicate comments, and unsupported labels', () => {
  assert.throws(() => parseCopilotResponse('not JSON', [comment]), /valid JSON/);

  for (const invalidFinding of [
    { ...finding, comment_id: 999 },
    { ...finding, title: 'English title' },
    { ...finding, label: 'feature' },
  ]) {
    assert.throws(
      () => parseCopilotResponse(JSON.stringify({ findings: [invalidFinding] }), [comment]),
    );
  }

  assert.throws(
    () => parseCopilotResponse(JSON.stringify({ findings: [finding, finding] }), [comment]),
    /more than one finding/,
  );
});

test('builds issue bodies in the selected form layout with original source links', () => {
  const body = buildIssueBody({
    finding,
    review,
    comment,
    pullRequestUrl: event.pull_request.html_url,
    parentIssueUrl: 'https://github.com/example/project/issues/3',
  });
  assert.match(body, /## 버그\/오류 제보/);
  assert.match(body, /### 버전[\s\S]*리뷰에서 제공되지 않음/);
  assert.match(body, /실제 동작[\s\S]*대기 시간 초과가 무시됩니다/);
  assert.match(body, /pull\/9/);
  assert.match(body, /pullrequestreview-321/);
  assert.match(body, /discussion_r654/);
  assert.match(body, /src\/Connection\.py:42/);
  assert.match(body, /issues\/3/);

  const fixBody = buildIssueBody({
    finding: {
      ...finding,
      label: 'fix',
      formFields: {
        change_type: '일반 변경',
        purpose: null,
        proposed_changes: null,
        scope: null,
        hotfix_context: null,
        acceptance_criteria: null,
      },
    },
    review,
    comment,
    pullRequestUrl: event.pull_request.html_url,
    parentIssueUrl: 'https://github.com/example/project/issues/3',
  });
  assert.match(fixBody, /## 변경 제안/);
  assert.match(fixBody, /### 변경 유형/);
  assert.match(fixBody, /### 리뷰에서 정리한 문제\n`wait\(\)` 호출 시 대기 시간 초과가 무시됩니다/);
  assert.match(fixBody, /### 필요한 조치\n`wait\(\)`가 설정된 제한 시간을 적용하도록 수정해야 합니다/);

  const unclassifiedBody = buildIssueBody({
    finding: { ...finding, label: null },
    review,
    comment,
    pullRequestUrl: event.pull_request.html_url,
    parentIssueUrl: 'https://github.com/example/project/issues/3',
  });
  assert.match(unclassifiedBody, /## 리뷰 지적/);
});

test('preserves the classified problem and action when issue form fields are populated', () => {
  const body = buildIssueBody({
    finding: {
      ...finding,
      formFields: {
        version: 'Python 3.14',
        expected: '제한 시간이 반영되어야 합니다.',
        actual: '호출이 무한 대기합니다.',
        reproduction: 'wait(timeout=1)을 호출합니다.',
        environment: 'Ubuntu',
        additional: '로그에 timeout 누락이 표시됩니다.',
      },
    },
    review,
    comment,
    pullRequestUrl: event.pull_request.html_url,
    parentIssueUrl: 'https://github.com/example/project/issues/3',
  });

  assert.match(body, /### 실제 동작\n호출이 무한 대기합니다/);
  assert.match(body, /### 추가 정보\n로그에 timeout 누락이 표시됩니다/);
  assert.match(body, /### 리뷰에서 정리한 문제\n`wait\(\)` 호출 시 대기 시간 초과가 무시됩니다/);
  assert.match(body, /### 필요한 조치\n`wait\(\)`가 설정된 제한 시간을 적용하도록 수정해야 합니다/);
});

test('preserves form details stated in the review instead of replacing them with missing-value text', () => {
  const formFields = {
    version: 'Python 3.10',
    expected: 'wait(timeout=1)이 1초 안에 반환되어야 합니다.',
    actual: '`wait(timeout=1)`이 제한 시간 없이 대기합니다.',
    reproduction: '`wait(timeout=1)`을 호출합니다.',
    environment: 'Ubuntu 22.04',
    additional: null,
  };
  const [parsedFinding] = parseCopilotResponse(JSON.stringify({
    findings: [{ ...finding, form_fields: formFields }],
  }), [comment]);
  const body = buildIssueBody({
    finding: parsedFinding,
    review,
    comment,
    pullRequestUrl: event.pull_request.html_url,
    parentIssueUrl: 'https://github.com/example/project/issues/3',
  });
  assert.match(body, /### 버전\nPython 3\.10/);
  assert.match(body, /### 기대한 동작\nwait\(timeout=1\)이 1초 안에 반환되어야 합니다/);
  assert.match(body, /### 실제 동작\n`wait\(timeout=1\)`이 제한 시간 없이 대기합니다/);
  assert.match(body, /### 재현 방법\n`wait\(timeout=1\)`을 호출합니다/);
  assert.match(body, /### 실행 환경\nUbuntu 22\.04/);
  assert.match(body, /### 추가 정보\n`wait\(\)`가 설정된 제한 시간을 적용하도록 수정해야 합니다/);
});

test('adds only a classified bug or fix label to the issue payload', () => {
  assert.deepEqual(
    buildIssuePayload({ title: '불명확한 리뷰 지적', label: null }, '본문'),
    { title: '불명확한 리뷰 지적', body: '본문' },
  );
  assert.deepEqual(
    buildIssuePayload({ title: '변경 제안', label: 'fix' }, '본문'),
    { title: '변경 제안', body: '본문', labels: ['fix'] },
  );
});

test('rejects missing, invalid, or unsupported form field values', () => {
  const invalidFindings = [
    { ...finding, form_fields: undefined },
    { ...finding, form_fields: { ...finding.form_fields, version: 3 } },
    { ...finding, form_fields: { ...finding.form_fields, unknown: '값' } },
    {
      ...finding,
      label: 'fix',
      form_fields: {
        change_type: '잘못된 유형',
        purpose: null,
        proposed_changes: null,
        scope: null,
        hotfix_context: null,
        acceptance_criteria: null,
      },
    },
  ];
  for (const invalidFinding of invalidFindings) {
    assert.throws(
      () => parseCopilotResponse(JSON.stringify({ findings: [invalidFinding] }), [comment]),
    );
  }
});

test('skips non-submission events before making API calls', async () => {
  let called = false;
  const result = await processReview({
    event: { ...event, action: 'edited' },
    owner: 'example',
    repo: 'project',
    fetchImpl: async () => {
      called = true;
      throw new Error('API must not be called');
    },
  });
  assert.equal(result.skipped, true);
  assert.equal(called, false);
});

test('does not create issues for submitted reviews without review comments', async () => {
  const result = await processReview({
    event,
    owner: 'example',
    repo: 'project',
    fetchImpl: async (url) => {
      assert.equal(
        new URL(url).pathname,
        '/repos/example/project/pulls/9/comments',
      );
      return jsonResponse([]);
    },
  });
  assert.equal(result.findingCount, 0);
});

test('does not create issues when unresolved review comments are not actionable', async () => {
  const requested = [];
  const fetchImpl = async (url) => {
    const path = new URL(url).pathname;
    requested.push(path);
    if (path.endsWith('/pulls/9/comments')) {
      return jsonResponse([comment]);
    }
    if (path.endsWith('/graphql')) {
      return graphqlThreadsResponse([{
        isResolved: false,
        commentIds: [comment.id],
      }]);
    }
    throw new Error(`Unexpected API request: ${path}`);
  };
  const result = await processReview({
    event,
    owner: 'example',
    repo: 'project',
    fetchImpl,
    generate: async () => '{"findings":[]}',
  });
  assert.equal(result.findingCount, 0);
  assert.equal(requested.some((path) => path.endsWith('/issues')), false);
});

test('fails without creating an issue when the PR branch does not identify a parent issue', async () => {
  let generated = false;
  const fetchImpl = async (url) => {
    const path = new URL(url).pathname;
    if (path.endsWith('/pulls/9/comments')) {
      return jsonResponse([comment]);
    }
    if (path.endsWith('/graphql')) {
      return graphqlThreadsResponse([{
        isResolved: false,
        commentIds: [comment.id],
      }]);
    }
    throw new Error(`Unexpected API request: ${path}`);
  };

  await assert.rejects(
    processReview({
      event: {
        ...event,
        pull_request: { ...event.pull_request, head: { ref: 'feature/no-issue' } },
      },
      owner: 'example',
      repo: 'project',
      fetchImpl,
      generate: async () => {
        generated = true;
        return JSON.stringify({ findings: [finding] });
      },
    }),
    /does not identify one target issue/,
  );
  assert.equal(generated, true);
});

test('does not send resolved review thread comments to the classifier', async () => {
  let generated = false;
  const fetchImpl = async (url) => {
    const requestUrl = new URL(url);
    const path = requestUrl.pathname;
    if (path.endsWith('/pulls/9/comments')) {
      return jsonResponse([comment]);
    }
    if (path.endsWith('/graphql')) {
      return graphqlThreadsResponse([{
        isResolved: true,
        commentIds: [comment.id],
      }]);
    }
    throw new Error(`Unexpected API request: ${path}`);
  };

  const result = await processReview({
    event,
    owner: 'example',
    repo: 'project',
    fetchImpl,
    generate: async () => {
      generated = true;
      return JSON.stringify({ findings: [finding] });
    },
  });

  assert.equal(generated, false);
  assert.equal(result.findingCount, 0);
  assert.equal(result.created.length, 0);
});

test('processes first unresolved comments from any reviewer and creates a parent-linked issue', async () => {
  const latestComment = {
    ...comment,
    id: 4380292522,
    user: { login: 'human-reviewer' },
    html_url: 'https://github.com/yong5eon/DefPixel/pull/13#discussion_r4380292522',
  };
  const replyComment = {
    ...latestComment,
    id: 4380292523,
    body: 'This reply must not reach the classifier.',
    user: { login: 'copilot-pull-request-reviewer[bot]' },
    html_url: 'https://github.com/yong5eon/DefPixel/pull/13#discussion_r4380292523',
  };
  const resolvedComment = {
    ...latestComment,
    id: 4380292521,
    pull_request_review_id: 320,
    body: 'This resolved finding must not reach Copilot.',
  };
  const requests = [];
  let createdIssue;
  let linkedIssue;
  const fetchImpl = async (url, options = {}) => {
    const requestUrl = new URL(url);
    const path = requestUrl.pathname;
    requests.push({ path, method: options.method ?? 'GET' });

    if (path.endsWith('/pulls/13/comments')) {
      return jsonResponse([resolvedComment, latestComment, replyComment]);
    }
    if (path === '/graphql') {
      const { query, variables } = JSON.parse(options.body);
      assert.match(query, /fullDatabaseId/);
      if (variables.after === null) {
        return graphqlThreadsResponse([{
          id: 'resolved-thread',
          isResolved: true,
          commentIds: [resolvedComment.id],
        }], { hasNextPage: true, endCursor: 'threads-page-2' });
      }
      assert.equal(variables.after, 'threads-page-2');
      return graphqlThreadsResponse([{
        id: 'unresolved-thread',
        isResolved: false,
        commentIds: [latestComment.id],
      }]);
    }
    if (path.endsWith('/issues/9')) {
      return jsonResponse({
        number: 9,
        html_url: 'https://github.com/yong5eon/DefPixel/issues/9',
      });
    }
    if (path === '/repos/yong5eon/DefPixel/issues' && options.method === 'POST') {
      const payload = JSON.parse(options.body);
      createdIssue = {
        id: 900,
        number: 91,
        html_url: 'https://github.com/yong5eon/DefPixel/issues/91',
        body: payload.body,
      };
      return jsonResponse(createdIssue, 201);
    }
    if (path.endsWith('/issues/9/sub_issues') && options.method === 'POST') {
      linkedIssue = JSON.parse(options.body).sub_issue_id;
      return jsonResponse({}, 201);
    }
    throw new Error(`Unexpected API request: ${options.method ?? 'GET'} ${path}`);
  };

  const result = await processReview({
    event: {
      ...event,
      pull_request: {
        ...event.pull_request,
        number: 13,
        html_url: 'https://github.com/yong5eon/DefPixel/pull/13',
        head: { ref: 'bug/9' },
      },
    },
    owner: 'yong5eon',
    repo: 'DefPixel',
    fetchImpl,
    generate: async (prompt) => {
      assert.doesNotMatch(prompt, /This resolved finding must not reach Copilot/);
      assert.doesNotMatch(prompt, /This reply must not reach the classifier/);
      assert.match(prompt, /The timeout is ignored when `wait\(\)` is called/);
      return JSON.stringify({
        findings: [{
          ...finding,
          comment_id: latestComment.id,
          title: 'Python 3.10 테스트 기대 오류 수정',
          problem: 'Python 3.10에서는 `time.fromisoformat()`이 `Z` 접미사를 처리하지 못해 테스트가 실패합니다.',
          action: 'Python 버전에 따라 테스트 기대값을 분리해야 합니다.',
          form_fields: {
            version: 'Python 3.10',
            expected: null,
            actual: null,
            reproduction: null,
            environment: '네 개의 PostgreSQL CI 구성',
            additional: null,
          },
        }],
      });
    },
  });

  assert.equal(result.findingCount, 1);
  assert.equal(result.created[0].number, 91);
  assert.equal(linkedIssue, 900);
  assert.match(createdIssue.body, /pull\/13/);
  assert.match(createdIssue.body, /pullrequestreview-321/);
  assert.match(createdIssue.body, /discussion_r4380292522/);
  assert.match(createdIssue.body, /src\/Connection\.py:42/);
  assert.match(createdIssue.body, /issues\/9/);
  assert.match(createdIssue.body, /### 버전\nPython 3\.10/);
  assert.match(createdIssue.body, /### 실행 환경\n네 개의 PostgreSQL CI 구성/);
  assert.equal(requests.some(({ path }) => path.includes('/issues?state=all')), false);
  assert.equal(requests.filter(({ path }) => path === '/graphql').length, 2);
});

test('propagates GraphQL errors instead of processing comments without resolution status', async () => {
  const fetchImpl = async (url) => {
    const path = new URL(url).pathname;
    if (path.endsWith('/pulls/9/comments')) {
      return jsonResponse([comment]);
    }
    if (path.endsWith('/graphql')) {
      return jsonResponse({ errors: [{ message: 'Resource not accessible' }] });
    }
    throw new Error(`Unexpected API request: ${path}`);
  };

  await assert.rejects(
    processReview({
      event,
      owner: 'example',
      repo: 'project',
      fetchImpl,
      generate: async () => JSON.stringify({ findings: [finding] }),
    }),
    /GitHub GraphQL API returned errors: Resource not accessible/,
  );
});

test('rejects missing Copilot credentials without using the API token', async (t) => {
  const previous = process.env.COPILOT_GITHUB_TOKEN;
  t.after(() => {
    if (previous === undefined) {
      delete process.env.COPILOT_GITHUB_TOKEN;
    } else {
      process.env.COPILOT_GITHUB_TOKEN = previous;
    }
  });
  delete process.env.COPILOT_GITHUB_TOKEN;
  await assert.rejects(runCopilot('prompt', () => {
    assert.fail('Copilot must not start without its own credentials');
  }), /COPILOT_GITHUB_TOKEN is not configured/);
});

test('isolates Copilot authentication and redacts both tokens from bounded stderr', async (t) => {
  const token = 'test-secret-token';
  const appToken = 'test-app-token';
  const previousApiToken = process.env.GITHUB_TOKEN;
  const previousCopilotToken = process.env.COPILOT_GITHUB_TOKEN;
  t.after(() => {
    process.env.GITHUB_TOKEN = previousApiToken;
    if (previousCopilotToken === undefined) {
      delete process.env.COPILOT_GITHUB_TOKEN;
    } else {
      process.env.COPILOT_GITHUB_TOKEN = previousCopilotToken;
    }
  });
  const ghToken = `ghp_${'a'.repeat(36)}`;
  const spawnProcess = (_command, _args, options) => {
    assert.deepEqual(options.stdio, ['pipe', 'pipe', 'pipe']);
    assert.equal(options.env.GITHUB_TOKEN, token);
    assert.equal(Object.values(options.env).includes(appToken), false);
    const child = Object.assign(new EventEmitter(), {
      stdin: new PassThrough(),
      stdout: new PassThrough(),
      stderr: new PassThrough(),
    });
    setImmediate(() => {
      child.stderr.end(`Authentication failed for ${token}; ${appToken}; invalid ${ghToken}\n${'x'.repeat(9000)}`);
      child.stdout.end();
      setImmediate(() => child.emit('close', 1));
    });
    return child;
  };
  process.env.GITHUB_TOKEN = appToken;
  process.env.COPILOT_GITHUB_TOKEN = token;

  await assert.rejects(
    runCopilot('prompt', spawnProcess),
    (error) => {
      assert.match(error.message, /Authentication failed/);
      assert.match(error.message, /\[REDACTED\]/);
      assert.match(error.message, /\[truncated\]/);
      assert.ok(error.message.length < 9000);
      assert.doesNotMatch(error.message, /test-secret-token|test-app-token|ghp_[A-Za-z0-9_]+/);
      return true;
    },
  );
});

test('propagates GitHub API failures instead of reporting success', async () => {
  await assert.rejects(
    processReview({
      event,
      owner: 'example',
      repo: 'project',
      fetchImpl: async () => new Response('API unavailable', { status: 503 }),
    }),
    /failed \(503\)/,
  );
});
