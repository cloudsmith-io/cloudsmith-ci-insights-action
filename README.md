# Cloudsmith Package Insights Action

This composite GitHub Action provides the Package Insights action tool. This tool analyzes the output of package installation logs and offers developers additional information and context when debugging workflows.

The action can be used in one of two ways:

1. By providing log text directly, or
1. By providing the name of another job in the same workflow run, whose logs will be fetched automatically via the GitHub API and passed to the underlying action.

## Use cases

Cloudsmith provides several ways to prevent package downloads when they're deemed unsafe. These include blocking downloads of the package before 
it's been scanned for vulnerabilities and quarantining packages if they're found to contain malware.

Notably, customers can quarantine their own packages through the Enterprise Policy Management system. This action will notify developers if their
downloads have been prevented due to a policy created by their organization. 

## Inputs

| Name | Required | Description |
|------|----------|-------------|
| `api-key` | Yes | Cloudsmith API key (exported to the underlying action as `CLOUDSMITH_API_KEY`). |
| `log` | No* | Raw build/install log text or a single line of URLs. Mutually exclusive with `job-name`. |
| `job-name` | No* | The name of another job (exact `name:` value) in the same workflow run. Mutually exclusive with `log`. |
| `follow-up` | No | Extra instructions to display in the output (e.g. Slack channel or contact). |

*You must provide exactly one of `log` or `job-name`.

## Behavior

- If `log` is supplied, it is forwarded directly.
- If `job-name` is supplied, the action:
  - Lists jobs for the current `run_id`.
  - Finds the job with the matching name.
  - Downloads the workflow run logs archive (`gh api .../logs`).
  - Extracts and concatenates log files for that job.
  - Writes the concatenated content to `job.log`.
  - Passes the file path (`job.log`) to the base action so it can read the file directly (avoids GitHub output truncation limits).

## Usage Examples

### A. Direct Log Input
```yaml
jobs:
  insights_direct:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run insights with provided logs
        uses: cloudsmith-io/cloudsmith-ci-insights-action@main
        with:
          api-key: ${{ secrets.CLOUDSMITH_API_KEY }}
          log: |
            Fetching package...
            Received 403 for package cloudsmith/example/pkg
```

### B. Using Job Name
```yaml
jobs:
  build:
    name: Build Job
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: |
          echo "Pretend build that fails to fetch a package" >&2
          echo "403 GET https://dl.cloudsmith.io/..." >&2
      - run: sleep 2

  analyze:
    runs-on: ubuntu-latest
    needs: build
    steps:
      - uses: actions/checkout@v4
      - name: Analyze build job logs
        uses: cloudsmith-io/cloudsmith-ci-insights-action@main
        with:
          api-key: ${{ secrets.CLOUDSMITH_API_KEY }}
          job-name: Build Job
```

## Notes / Limitations

- The wrapper uses the `octokit` SDK with the automatically provided `GITHUB_TOKEN` to retrieve logs.
- Very large logs are written to a file and the file path is passed (not the contents), avoiding step output truncation. Extremely huge logs may still risk disk space/time; consider filtering if multi-megabyte.
- Matching is exact on the `name:` you set for the job (case sensitive per API response). Ensure consistency.

