# Package Insights Python CLI

This is a Python Click application to check the quarantine state of one or more Cloudsmith packages using the Cloudsmith API.

## Usage

Install dependencies:
```
pip install -r requirements
```

Run the CLI:
```
python package_insights.py <logfile>
```

You must set the `CLOUDSMITH_API_KEY` environment variable with your Cloudsmith API key.
