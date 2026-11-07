import { readFile } from 'node:fs/promises';
import { join, posix, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const API_URL = 'https://api.github.com';
const MAX_PR_BODY_LENGTH = 65536;
const ISSUE_TYPES = new Set(['bug', 'fix', 'feature', 'task']);
const ISSUE_DOCUMENTS = [
  'CHANGELOG.md',
  'IR.md',
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
    if (/^(?:[a-z][a-z0-9+.-]*:|\/\/|#)/i.test(value)) {
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

export function buildPullRequest({ documents, issueDirectory, owner, repo, sha }) {
  const markdown = documents['IR.md'];
  if (!markdown?.trim()) {
    throw new Error(`PR body is missing or empty: ${issueDirectory}/IR.md`);
  }
  const heading = /^#[ \t]+([^\r\n]+)(?:\r?\n|$)/.exec(markdown);
  const title = heading?.[1].trim();
  if (!title || title.length > 256) {
    throw new Error(`PR title must be a non-empty first-line heading of at most 256 characters: ${issueDirectory}/IR.md`);
  }
  const bodyMarkdown = markdown.slice(heading[0].length);
  if (!bodyMarkdown.trim()) {
    throw new Error(`PR body is missing or empty: ${issueDirectory}/IR.md`);
  }
  const lines = bodyMarkdown.trim().split(/\r?\n/).filter((line) => line.trim());
  if (lines.at(-1) !== `- Changes: ${issueDirectory}/CHANGELOG.md`) {
    throw new Error(`IR document must end with the changelog entry: ${issueDirectory}/IR.md`);
  }
  const body = resolveDocumentLinks(bodyMarkdown, `${issueDirectory}/IR.md`, owner, repo, sha).trim();
  if (body.length > MAX_PR_BODY_LENGTH) {
    throw new Error(`PR body exceeds the ${MAX_PR_BODY_LENGTH}-character limit`);
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

async function findPullRequestIssueDirectory(repositoryPath, pullRequestNumber, token, fetchImpl) {
  const candidates = [];
  for (let page = 1; page <= 30; page += 1) {
    const files = await githubRequest(
      `${repositoryPath}/pulls/${pullRequestNumber}/files?per_page=100&page=${page}`,
      token,
      fetchImpl,
    );
    if (!Array.isArray(files)) {
      throw new Error('GitHub API did not return the pull request file list');
    }
    for (const file of files) {
      if (typeof file?.filename !== 'string' || typeof file.status !== 'string') {
        throw new Error('GitHub API returned an invalid pull request file');
      }
      if (file.status !== 'removed'
        && /^issues\/(?:bug|fix|feature|task)\/[A-Za-z0-9][A-Za-z0-9._-]*\/IR\.md$/.test(file.filename)) {
        candidates.push(file.filename.slice(0, -'/IR.md'.length));
      }
    }
    if (files.length < 100) {
      if (candidates.length !== 1) {
        throw new Error(`Expected exactly one changed issue IR.md, found ${candidates.length} in PR #${pullRequestNumber}`);
      }
      return candidates[0];
    }
  }
  throw new Error(`Pull request file list reached GitHub's 3000-file limit: PR #${pullRequestNumber}`);
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
  return { labels, assignees, milestone: issue.milestone, nodeId: issue.node_id };
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

  const agentBranch = /^(?:copilot|codex)\/.+$/.test(branch);
  let issueDirectory = agentBranch ? null : parseIssueBranch(branch);
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
  const existing = openPullRequests[0];
  if (openPullRequests.length > 0) {
    if (!Number.isInteger(existing?.number)) {
      throw new Error('GitHub API returned an open pull request without a number');
    }
    if (typeof existing.node_id !== 'string' || !existing.node_id) {
      throw new Error('GitHub API did not return a node ID for the open pull request');
    }
    if (agentBranch) {
      if (openPullRequests.length !== 1) {
        throw new Error('GitHub API returned multiple open pull requests for the agent branch');
      }
      if (typeof existing.head?.sha !== 'string' || !existing.head.sha) {
        throw new Error('GitHub API did not return the agent pull request head SHA');
      }
      if (existing.head.sha !== sha) {
        return { status: 'stale-agent-push' };
      }
      issueDirectory = await findPullRequestIssueDirectory(
        encodedRepository,
        existing.number,
        token,
        fetchImpl,
      );
    }
  } else {
    if (agentBranch) {
      return { status: 'no-open-agent-pull-request' };
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
  }

  let metadata;
  if (!agentBranch) {
    metadata = await getIssueMetadata(encodedRepository, issueDirectory, token, fetchImpl);
  }
  const documents = {};
  for (const fileName of ISSUE_DOCUMENTS) {
    documents[fileName] = await readOptionalFile(join(rootDirectory, issueDirectory, fileName));
  }
  if (!documents['CHANGELOG.md'].trim()) {
    throw new Error(`Changelog is missing or empty: ${issueDirectory}/CHANGELOG.md`);
  }
  const pullRequest = buildPullRequest({
    documents,
    issueDirectory,
    owner,
    repo,
    sha,
  });

  if (openPullRequests.length > 0) {
    await githubRequest(
      `${encodedRepository}/pulls/${existing.number}`,
      token,
      fetchImpl,
      {
        method: 'PATCH',
        body: JSON.stringify({ title: pullRequest.title, body: pullRequest.body }),
      },
    );
    if (agentBranch) {
      return { status: 'already-open', number: existing.number };
    }
    const { labels, assignees, milestone, nodeId: issueNodeId } = metadata;
    await addPullRequestLabels(encodedRepository, existing.number, labels, token, fetchImpl);
    await addPullRequestAssignees(encodedRepository, existing.number, assignees, token, fetchImpl);
    await setPullRequestMilestone(encodedRepository, existing.number, milestone, token, fetchImpl);
    await linkPullRequestToIssue(issueNodeId, existing.node_id, token, fetchImpl);
    return { status: 'already-open', number: existing.number };
  }

  const { labels, assignees, milestone, nodeId: issueNodeId } = metadata;
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
        draft: true,
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
    console.log(`Updated pull request #${result.number} for this branch and base`);
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
