const core = require('@actions/core');
const github = require('@actions/github');
const { writeFileSync } = require('fs');

async function run() {
  try {
    const jobName = core.getInput('job-name', { required: true });
    const maxRetries = parseInt(core.getInput('max-retries') || '5', 10);
    const retryDelay = parseInt(core.getInput('retry-delay-seconds') || '3', 10) * 1000;

    const token = process.env.GITHUB_TOKEN || process.env.GH_TOKEN || process.env.GITHUB_TOKEN_ACTION || '';
    if (!token) {
      core.setFailed('Missing GITHUB_TOKEN. Set permissions: actions: read');
      return;
    }

    const octokit = github.getOctokit(token);
    const { owner, repo } = github.context.repo;
    const runId = github.context.runId;

    core.info(`Locating job '${jobName}' in run ${runId}`);
    const jobsResp = await octokit.rest.actions.listJobsForWorkflowRun({ owner, repo, run_id: runId, per_page: 100 });
    let job = jobsResp.data.jobs.find(j => j.name === jobName);
    if (!job) {
      core.setFailed(`Job '${jobName}' not found in workflow run ${runId}`);
      return;
    }
    core.info(`Found job id: ${job.id}`);

    let attempt = 0;
    let logsBuffer = null;
    while (attempt < maxRetries) {
      attempt++;
      try {
        core.info(`Attempt ${attempt}/${maxRetries} downloading logs for job ${job.id}`);
        const logResp = await octokit.rest.actions.downloadJobLogsForWorkflowRun({ owner, repo, job_id: job.id });
        logsBuffer = logResp.data; // Buffer
        if (logsBuffer && logsBuffer.length > 0) {
          break;
        }
      } catch (err) {
        core.warning(`Fetch attempt ${attempt} failed: ${err.message}`);
      }
      if (attempt < maxRetries) {
        await new Promise(r => setTimeout(r, retryDelay));
      }
    }

    if (!logsBuffer) {
      core.setFailed(`Failed to fetch logs for job ${jobName} after ${maxRetries} attempts`);
      return;
    }

    const fullText = logsBuffer.toString('utf8');
    const outPath = 'fetched_job.log';
    writeFileSync(outPath, fullText, { encoding: 'utf8' });
    const snippet = fullText.split(/\r?\n/).slice(0, 20).join('\n');

    core.setOutput('log-path', outPath);
    core.setOutput('log-snippet', snippet);
    core.info(`Wrote ${fullText.length} bytes to ${outPath}`);
  } catch (err) {
    core.setFailed(err.message);
  }
}

run();
