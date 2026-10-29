import { readFile } from 'node:fs/promises';
import { join, posix, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const API_URL = 'https://api.github.com';
const MAX_PR_BODY_LENGTH = 65536;
const ISSUE_TYPES = new Set(['bug', 'fix', 'feature', 'task']);
const ISSUE_DOCUMENTS = [
  'README.md',
  'REQUIREMENTS.md',
  'CHANGELOG.md',
  'IMPLEMENTS.md',
  'TASKS.md',
];

export function parseIssueBranch(branch) {
  const match = /^(bug|fix|feature|task)\/([A-Za-z0-9][A-Za-z0-9._-]*)$/.exec(branch);
  if (!match || !ISSUE_TYPES.has(match[1])) {
    throw new Error(`Branch "${branch}" does not identify a supported issue directory`);
  }
  return `issues/${match[1]}/${match[2]}`;
}

async function readOptionalFile(path) {
  try {
    return await readFile(path, 'utf8');
  } catch (error) {
    if (error.code === 'ENOENT') {
      return '';
    }
    throw error;
  }
}

function sourceLink(owner, repo, sha, path) {
  const encodedPath = path.split('/').map(encodeURIComponent).join('/');
  return `https://github.com/${owner}/${repo}/blob/${sha}/${encodedPath}`;
}

function resolveDocumentLinks(markdown, documentPath, owner, repo, sha) {
  const destination = String.raw`<[^>\r\n]+>|[^\s()]+(?:\([^\s()]*\)[^\s()]*)*`;
  const tokens = new RegExp([
    String.raw`(?<fence>^ {0,3}(?<marker>\x60{3,}|~{3,})[^\n]*\n[\s\S]*?^ {0,3}\k<marker>[ \t]*\r?$)`,
    String.raw`(?<code>(?<ticks>\x60+)(?!\x60)[\s\S]*?\k<ticks>(?!\x60))`,
    String.raw`(?<definition>(?<definitionPrefix>^ {0,3}\[(?<key>[^\]\r\n]+)\]:[ \t]*)(?<target>${destination})(?<title>[^\r\n]*))`,
    String.raw`(?<inline>\]\([ \t]*)(?<url>${destination})`,
    String.raw`(?<reference>!?\[(?<label>[^\]\r\n]+)\](?:\[(?<identifier>[^\]\r\n]*)\])?)(?!\()`,
  ].join('|'), 'gm');
  const definitions = new Map();
  const keyOf = (value) => value.trim().replace(/\s+/g, ' ').toLowerCase();
  const absolute = (target) => {
    const angled = target.startsWith('<');
    const value = angled ? target.slice(1, -1) : target;
    if (/^(?:[a-z][a-z0-9+.-]*:|\/\/)/i.test(value)) {
      return target;
    }
    const suffixIndex = value.search(/[?#]/);
    const path = suffixIndex < 0 ? value : value.slice(0, suffixIndex);
    const suffix = suffixIndex < 0 ? '' : value.slice(suffixIndex);
    const resolved = path
      ? posix.normalize(path.startsWith('/') ? path.slice(1) : posix.join(posix.dirname(documentPath), path))
      : documentPath;
    if (resolved === '..' || resolved.startsWith('../')) {
      throw new Error(`Markdown link escapes the repository in ${documentPath}: ${target}`);
    }
    const encoded = resolved.split('/').map((part) => encodeURIComponent(decodeURIComponent(part))).join('/');
    const url = `https://github.com/${owner}/${repo}/blob/${sha}/${encoded}${suffix}`;
    return angled ? `<${url}>` : url;
  };
  for (const match of markdown.matchAll(tokens)) {
    if (match.groups.definition && !definitions.has(keyOf(match.groups.key))) {
      definitions.set(keyOf(match.groups.key), {
        target: match.groups.target,
        title: match.groups.title,
      });
    }
  }
  return markdown.replace(tokens, (match, ...args) => {
    const groups = args.at(-1);
    if (groups.fence || groups.code) {
      return match;
    }
    if (groups.inline) {
      return `${groups.inline}${absolute(groups.url)}`;
    }
    if (groups.definition) {
      return `${groups.definitionPrefix}${absolute(groups.target)}${groups.title}`;
    }
    const definition = definitions.get(keyOf(groups.identifier || groups.label));
    if (!definition) {
      return match;
    }
    const image = match.startsWith('!') ? '!' : '';
    return `${image}[${groups.label}](${absolute(definition.target)}${definition.title})`;
  });
}

export function buildPullRequest({ template, documents, issue, issueDirectory, owner, repo, sha }) {
  const issueType = issueDirectory.split('/')[1];
  const documentTitle = /^#[ \t]+(.+)$/m.exec(documents['README.md'] ?? '')?.[1].trim();
  const title = documentTitle && documentTitle.length <= 256 ? documentTitle : issue?.title?.trim();
  if (!title || title.length > 256 || /[\r\n]/.test(title)) {
    throw new Error('The source issue must provide a PR title of at most 256 characters');
  }

  const linkedDocuments = {};
  for (const [fileName, markdown] of Object.entries(documents)) {
    if (markdown.trim()) {
      linkedDocuments[fileName] = resolveDocumentLinks(markdown, `${issueDirectory}/${fileName}`, owner, repo, sha);
    }
  }
  const changeType = {
    bug: '버그 수정 및 일반 변경, 핫픽스 처리',
    fix: '버그 수정 및 일반 변경, 핫픽스 처리',
    feature: '기능 추가',
    task: '기타',
  }[issueType];
  if (!changeType) {
    throw new Error(`Unsupported issue type "${issueType}"`);
  }
  const checkbox = `- [ ] ${changeType}`;
  const issueNumber = issueDirectory.split('/')[2];
  const issueLink = `https://github.com/${owner}/${repo}/issues/${issueNumber}`;
  const render = (includeContent, includeTemplate = true) => {
    const summary = [`원본 이슈: [#${issueNumber}](${issueLink})`];
    const validation = [];
    if (!includeContent) {
      summary.push('PR 본문 길이 제한으로 문서와 이슈의 내용은 아래 원문 링크에서 제공합니다.');
    }
    if (!includeTemplate) {
      summary.push(`PR 템플릿도 길이 제한을 초과하여 [템플릿 원문](${sourceLink(owner, repo, sha, '.github/PULL_REQUEST_TEMPLATE.md')})으로 제공합니다.`);
    }
    for (const [fileName, markdown] of Object.entries(linkedDocuments)) {
      const link = sourceLink(owner, repo, sha, `${issueDirectory}/${fileName}`);
      const record = includeContent
        ? `<details>\n<summary>${fileName}</summary>\n\n${markdown}\n\n[원문](${link})\n\n</details>`
        : `[${fileName}](${link})`;
      (fileName === 'TASKS.md' ? validation : summary).push(record);
    }
    if (Object.keys(linkedDocuments).length === 0) {
      summary.push('첨부된 작업 문서가 없어 원본 이슈를 기준으로 작성했습니다.');
      if (includeContent && issue?.body) {
        summary.push(issue.body);
      }
    }
    if (validation.length === 0) {
      validation.push('별도 작업·검증 문서가 첨부되지 않았습니다. 검증 수행 여부는 원본 이슈와 첨부 문서를 확인해 주세요.');
    }
    const sections = new Map([
      ['<!-- 무엇을 왜 변경했는지 간단히 요약해 주세요. -->', {
        heading: '## 변경 내용', content: summary.join('\n\n'),
      }],
      ['<!-- 실행한 테스트와 결과를 작성해 주세요. 테스트를 실행하지 않았다면 사유를 적어 주세요. -->', {
        heading: '## 검증', content: validation.join('\n\n'),
      }],
    ]);
    let body = (includeTemplate ? template : '').replace(checkbox, `- [X] ${changeType}`).replace(
      /<!-- 무엇을 왜 변경했는지 간단히 요약해 주세요\. -->|<!-- 실행한 테스트와 결과를 작성해 주세요\. 테스트를 실행하지 않았다면 사유를 적어 주세요\. -->/g,
      (placeholder) => {
        const section = sections.get(placeholder);
        section.inserted = true;
        return section.content;
      },
    );
    for (const section of sections.values()) {
      if (!section.inserted) {
        body += `\n\n${section.heading}\n\n${section.content}`;
      }
    }
    return `${body.trim()}\n\nCloses #${issueNumber}`;
  };
  let body = render(true);
  if (body.length > MAX_PR_BODY_LENGTH) {
    body = render(false);
  }
  if (body.length > MAX_PR_BODY_LENGTH) {
    body = render(false, false);
  }
  return { title, body };
}

async function githubRequest(path, token, fetchImpl, options = {}) {
  const response = await fetchImpl(`${API_URL}${path}`, {
    ...options,
    headers: {
      Accept: 'application/vnd.github+json',
      Authorization: `Bearer ${token}`,
      'X-GitHub-Api-Version': '2022-11-28',
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
  });
  const responseText = await response.text();
  let result;
  try {
    result = responseText ? JSON.parse(responseText) : null;
  } catch (error) {
    throw new Error(`GitHub API returned invalid JSON for ${path}`, { cause: error });
  }
  if (!response.ok) {
    throw new Error(`GitHub API request failed (${response.status}): ${result?.message ?? 'unknown error'}`);
  }
  return result;
}

async function githubGraphqlRequest(query, variables, token, fetchImpl) {
  const response = await fetchImpl(`${API_URL}/graphql`, {
    method: 'POST',
    headers: {
      Accept: 'application/vnd.github+json',
      Authorization: `Bearer ${token}`,
      'X-GitHub-Api-Version': '2022-11-28',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query, variables }),
  });
  const responseText = await response.text();
  let result;
  try {
    result = responseText ? JSON.parse(responseText) : null;
  } catch (error) {
    throw new Error('GitHub GraphQL API returned invalid JSON', { cause: error });
  }
  if (!response.ok || result?.errors?.length) {
    const message = result?.errors?.map((entry) => entry.message).join('; ')
      || 'unknown error';
    throw new Error(`GitHub GraphQL API request failed (${response.status}): ${message}`);
  }
  return result?.data;
}

async function getIssueMetadata(repositoryPath, issueDirectory, token, fetchImpl) {
  const issueNumber = issueDirectory.split('/')[2];
  const issue = await githubRequest(
    `${repositoryPath}/issues/${encodeURIComponent(issueNumber)}`,
    token,
    fetchImpl,
  );
  if (!Array.isArray(issue?.labels)) {
    throw new Error(`GitHub API did not return labels for issue #${issueNumber}`);
  }
  const labels = issue.labels.map((label) => {
    if (typeof label?.name !== 'string' || !label.name) {
      throw new Error(`GitHub API returned an invalid label for issue #${issueNumber}`);
    }
    return label.name;
  });
  if (!Array.isArray(issue?.assignees)) {
    throw new Error(`GitHub API did not return assignees for issue #${issueNumber}`);
  }
  if (typeof issue.node_id !== 'string' || !issue.node_id) {
    throw new Error(`GitHub API did not return a node ID for issue #${issueNumber}`);
  }
  const assignees = issue.assignees.map((assignee) => {
    if (typeof assignee?.login !== 'string' || !assignee.login) {
      throw new Error(`GitHub API returned an invalid assignee for issue #${issueNumber}`);
    }
    return assignee.login;
  });
  if (issue.milestone !== null
    && (!Number.isSafeInteger(issue.milestone?.number) || issue.milestone.number <= 0)) {
    throw new Error(`GitHub API returned an invalid milestone for issue #${issueNumber}`);
  }
  return { labels, assignees, milestone: issue.milestone, nodeId: issue.node_id, issue };
}

async function addPullRequestLabels(repositoryPath, pullRequestNumber, labels, token, fetchImpl) {
  if (labels.length === 0) {
    return;
  }
  await githubRequest(
    `${repositoryPath}/issues/${pullRequestNumber}/labels`,
    token,
    fetchImpl,
    {
      method: 'POST',
      body: JSON.stringify({ labels }),
    },
  );
}

async function addPullRequestAssignees(
  repositoryPath,
  pullRequestNumber,
  assignees,
  token,
  fetchImpl,
) {
  if (assignees.length === 0) {
    return;
  }
  await githubRequest(
    `${repositoryPath}/issues/${pullRequestNumber}/assignees`,
    token,
    fetchImpl,
    {
      method: 'POST',
      body: JSON.stringify({ assignees }),
    },
  );
}

async function setPullRequestMilestone(
  repositoryPath,
  pullRequestNumber,
  milestone,
  token,
  fetchImpl,
) {
  if (milestone === null) {
    return;
  }
  const updated = await githubRequest(
    `${repositoryPath}/issues/${pullRequestNumber}`,
    token,
    fetchImpl,
    {
      method: 'PATCH',
      body: JSON.stringify({ milestone: milestone.number }),
    },
  );
  if (updated?.milestone?.number !== milestone.number) {
    throw new Error(`GitHub API did not confirm milestone ${milestone.number} for PR #${pullRequestNumber}`);
  }
}

async function linkPullRequestToIssue(issueNodeId, pullRequestNodeId, token, fetchImpl) {
  const data = await githubGraphqlRequest(
    `mutation AddCloseIssueReferences($input: AddCloseIssueReferencesInput!) {
      addCloseIssueReferences(input: $input) {
        issue { id }
      }
    }`,
    {
      input: {
        issueId: issueNodeId,
        pullRequestIds: [pullRequestNodeId],
      },
    },
    token,
    fetchImpl,
  );
  if (data?.addCloseIssueReferences?.issue?.id !== issueNodeId) {
    throw new Error('GitHub GraphQL API did not confirm the issue-pull request link');
  }
}

export async function createPullRequest({
  owner,
  repo,
  branch,
  base,
  sha,
  token,
  rootDirectory = process.cwd(),
  fetchImpl = fetch,
}) {
  if (!owner || !repo || !base || !sha || !token) {
    throw new Error('Missing repository, base, commit, or token context');
  }
  if (branch === base) {
    return { status: 'default-branch' };
  }

  const issueDirectory = parseIssueBranch(branch);
  const encodedRepository = `/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}`;
  const query = new URLSearchParams({
    state: 'open',
    head: `${owner}:${branch}`,
    base,
    per_page: '100',
  });
  const openPullRequests = await githubRequest(
    `${encodedRepository}/pulls?${query}`,
    token,
    fetchImpl,
  );
  if (!Array.isArray(openPullRequests)) {
    throw new Error('GitHub API did not return the open pull request list');
  }
  if (openPullRequests.length > 0) {
    if (!Number.isInteger(openPullRequests[0]?.number)) {
      throw new Error('GitHub API returned an open pull request without a number');
    }
    if (typeof openPullRequests[0]?.node_id !== 'string' || !openPullRequests[0].node_id) {
      throw new Error('GitHub API did not return a node ID for the open pull request');
    }
    const { labels, assignees, milestone, nodeId: issueNodeId } = await getIssueMetadata(
      encodedRepository,
      issueDirectory,
      token,
      fetchImpl,
    );
    await addPullRequestLabels(
      encodedRepository,
      openPullRequests[0].number,
      labels,
      token,
      fetchImpl,
    );
    await addPullRequestAssignees(
      encodedRepository,
      openPullRequests[0].number,
      assignees,
      token,
      fetchImpl,
    );
    await setPullRequestMilestone(
      encodedRepository,
      openPullRequests[0].number,
      milestone,
      token,
      fetchImpl,
    );
    await linkPullRequestToIssue(
      issueNodeId,
      openPullRequests[0].node_id,
      token,
      fetchImpl,
    );
    return { status: 'already-open', number: openPullRequests[0].number };
  }

  const compare = await githubRequest(
    `${encodedRepository}/compare/${encodeURIComponent(base)}...${encodeURIComponent(sha)}`,
    token,
    fetchImpl,
  );
  if (!Number.isInteger(compare?.ahead_by) || compare.ahead_by < 0
    || !Array.isArray(compare.files)) {
    throw new Error('GitHub API did not return the branch comparison result');
  }
  if (compare.ahead_by === 0 || compare.files.length === 0) {
    return { status: 'no-changes' };
  }
  const headCommit = await githubRequest(
    `${encodedRepository}/git/commits/${encodeURIComponent(sha)}`,
    token,
    fetchImpl,
  );
  const baseTree = compare.base_commit?.commit?.tree?.sha;
  const headTree = headCommit?.tree?.sha;
  if (typeof baseTree !== 'string' || !baseTree
    || typeof headTree !== 'string' || !headTree) {
    throw new Error('GitHub API did not return the base and head commit tree SHAs');
  }
  if (baseTree === headTree) {
    return { status: 'no-changes' };
  }

  const { labels, assignees, milestone, nodeId: issueNodeId, issue } = await getIssueMetadata(
    encodedRepository,
    issueDirectory,
    token,
    fetchImpl,
  );
  const template = await readOptionalFile(join(rootDirectory, '.github', 'PULL_REQUEST_TEMPLATE.md'));
  const documents = {};
  for (const fileName of ISSUE_DOCUMENTS) {
    documents[fileName] = await readOptionalFile(join(rootDirectory, issueDirectory, fileName));
  }
  const pullRequest = buildPullRequest({
    template,
    documents,
    issue,
    issueDirectory,
    owner,
    repo,
    sha,
  });

  const created = await githubRequest(
    `${encodedRepository}/pulls`,
    token,
    fetchImpl,
    {
      method: 'POST',
      body: JSON.stringify({
        title: pullRequest.title,
        body: pullRequest.body,
        head: branch,
        base,
      }),
    },
  );
  if (!Number.isInteger(created?.number) || typeof created.html_url !== 'string') {
    throw new Error('GitHub API did not return the created pull request');
  }
  if (typeof created.node_id !== 'string' || !created.node_id) {
    throw new Error('GitHub API did not return a node ID for the created pull request');
  }
  await addPullRequestLabels(encodedRepository, created.number, labels, token, fetchImpl);
  await addPullRequestAssignees(
    encodedRepository,
    created.number,
    assignees,
    token,
    fetchImpl,
  );
  await setPullRequestMilestone(encodedRepository, created.number, milestone, token, fetchImpl);
  await linkPullRequestToIssue(issueNodeId, created.node_id, token, fetchImpl);
  return { status: 'created', number: created.number, url: created.html_url };
}

async function main() {
  const [owner, repo] = (process.env.GITHUB_REPOSITORY ?? '').split('/');
  const result = await createPullRequest({
    owner,
    repo,
    branch: process.env.GITHUB_REF_NAME,
    base: process.env.DEFAULT_BRANCH,
    sha: process.env.GITHUB_SHA,
    token: process.env.GITHUB_TOKEN,
  });
  if (result.status === 'created') {
    console.log(`Created pull request #${result.number}: ${result.url}`);
  } else if (result.status === 'already-open') {
    console.log(`Pull request #${result.number} is already open for this branch and base`);
  } else {
    console.log(`Skipped pull request creation: ${result.status}`);
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
