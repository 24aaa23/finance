# Main hybrid pipeline: Azure GPT-OSS 120B

This launcher uses the current main SQL+KG pipeline, original 1000-question dataset
and current context review rules. Only the model provider, endpoint, credentials
and deployment identifier change. Shared pipeline code and Bedrock launchers are
unchanged. No grader starts and no existing Bedrock report is reused.

## Credentials

```bash
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2
cp -n ablations/azure_gpt_oss_120b/azure.env.example \
  ablations/azure_gpt_oss_120b/azure.env
```

Open `ablations/azure_gpt_oss_120b/azure.env` in your editor and fill in:

```dotenv
AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE.openai.azure.com/
AZURE_FOUNDRY_ENDPOINT=
AZURE_OPENAI_API_KEY=YOUR-RESOURCE-KEY
AZURE_GPT_OSS_DEPLOYMENT=YOUR-EXACT-GPT-OSS-120B-DEPLOYMENT-NAME
```

Use the resource endpoint/key associated with your deployed GPT-OSS model. Model
requests use the deployment name, not the Bedrock model ID. If your deployment
instead lists a Foundry resource endpoint such as
`https://YOUR-RESOURCE.services.ai.azure.com/`, put it in `AZURE_FOUNDRY_ENDPOINT`
and leave `AZURE_OPENAI_ENDPOINT` empty. The latter takes precedence when both
are set. A Foundry project URL ending `/api/projects/...` is not the inference
endpoint. The launcher accepts a resource root or its `/openai/v1/` base URL and
normalizes it to `/openai/v1/`; legacy deployments and `/models` APIs are not used.
The v1 API needs no `api-version` setting.

`azure.env` is ignored by Git, loaded automatically, and never printed. Exported
environment variables take precedence over this file. Credentials are not saved
in the run manifest. You can alternatively put the same variables in the existing
project `.env`, although the dedicated file avoids interaction with older runs.

## Check and run

Offline configuration check, without inference:

```bash
bash ablations/azure_gpt_oss_120b/run_raw.sh without_context --dry-run
```

Test endpoint/deployment/key with one small billed request:

```bash
bash ablations/azure_gpt_oss_120b/run_raw.sh --check-connection
```

Main Fuseki must serve the main KG on port 3030, not Improvement 11's graph on
3041. If it is not running, start it in a separate terminal:

```bash
bash ablations/openai_gpt_6_1_sol/start_fuseki.sh
```

Run without optional context:

```bash
bash ablations/azure_gpt_oss_120b/run_raw.sh without_context \
  --run-tag run_01 --workers 2 --dag-workers 1
```

Or with the existing optional domain/business documents:

```bash
bash ablations/azure_gpt_oss_120b/run_raw.sh with_context \
  --run-tag run_01 --workers 2 --dag-workers 1
```

Context compilation/reuse and quarantine behave as in the main hybrid pipeline.
Two questions can run concurrently, each with one DAG node running at a time.
Repeat the identical command to resume under the existing core resume policy.
Use a fresh run tag when changing deployment, endpoint, workers, code or assets.

Outputs:
`ablations/azure_gpt_oss_120b/runs/gpt_oss_120b/<condition>/run_01/raw_pipeline.csv`.
Existing Bedrock runs remain separate. This integration does not redirect the
Improvement 10, Improvement 11 or combined-baseline launchers to Azure.

Reference: https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/endpoints
