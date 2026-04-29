# Vertex AI Setup

Denario agents built with LangGraph can be run using a Gemini API key (see above). However, agents built using [AG2](https://ag2.ai/) require a different setup to access Gemini models via the [Vertex AI](https://cloud.google.com/vertex-ai?hl=en) API.

If you plan to run the analysis module with Gemini models accessed through Vertex AI, for example:

```python
den.get_results(engineer_model='gemini-2.5-pro',
                researcher_model='gemini-2.5-pro')
```

the following steps are required:

1. **Create a Google service account key file** (JSON format; see instructions below).
2. **Download** the file to the machine where Denario will run.
3. **Rename** the file to `gemini.json`.
4. **Set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable** to the path of this file:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/gemini.json
```

This environment variable must be set whenever Denario requires Vertex AI access.

## Enabling Vertex AI

1. **Google Account**: If you do not have a Google account, create one [here](https://www.google.com/intl/en-GB/account/about/).
2. **Google Cloud Console**: Log in at [Google Cloud Console](https://console.cloud.google.com/).

## Create a Google Cloud Project

- Click "Select a project" (top left) and choose an existing project or click "New project" (top right) to create a new one (e.g., "denario").
- Once created, select the project.

## Enable Vertex AI API

- With the project selected, its name will appear next to the Google Cloud logo.
- Open the navigation menu (three horizontal lines), find "Vertex AI", hover, and select "Dashboard".
- Click "Enable all recommended APIs".

## Create a Service Account Key

- In the navigation menu, go to "IAM & Admin" > "Service Accounts".
- Click "Create Service Account".
- Name the account (e.g., "denario"). The description is optional.
- Click "Create and Continue".
- In "Select a Role", enter "Vertex AI User" and select it. Click "Continue".
- Skip "Principals with access". Click "Done".
- In the list view, find your account (e.g., `denario@denario-1234.iam.gserviceaccount.com`).
- Click the three dots under "Actions" and select "Manage Keys".
- Click "Add key" > "Create new key" > select "JSON".
- Download the JSON file and rename it to `gemini.json`.

## Enable Billing

- In the navigation menu, select "Billing".
- Click "Link a billing account" and follow the prompts to create a billing account.
- Choose your country, enter contact information, and add a payment method.
