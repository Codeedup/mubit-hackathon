# DeepSeek through OpenRouter

Robo Medic supports two distinct routes. Both use the same label-only classifier,
incident evidence, outcome workflow, and failure handling as the existing app.

## Create the account and key

1. Sign up at [OpenRouter](https://openrouter.ai/), using your preferred sign-in method.
2. Open [API keys](https://openrouter.ai/workspaces/default/keys) and create a named key for Robo Medic.
3. Give the key a small spending limit. Account credit and key limits are separate;
   a paid model needs available account credit. No credit purchase is automatic.
4. Put the key in the ignored local `.env`; do not put it in chat, source code, or screenshots.

## Direct OpenRouter connection

```dotenv
ROBO_MEDIC_PROVIDER=openrouter
OPENROUTER_API_KEY=<your OpenRouter key>
OPENROUTER_MODEL=deepseek/deepseek-v4.1-flash-1017
```

Restart the backend. The diagnosis action reads **Diagnose through OpenRouter**.
The server sends `/api/v1/chat/completions` with bearer authentication, fixed
instructions, and the label-free incident. It disables reasoning and caps output
at 128 tokens. It stores the real OpenRouter generation ID, model ID, and raw
label. This route does not send inference or feedback to Mubit.

The model ID was present in OpenRouter's public model catalog on 24 November 2026.
Availability and prices can change; select an available model your account permits.

## Through Mubit

In Mubit, add the OpenRouter key under **Provider keys → OpenAI-compatible → OpenRouter**.
Create a Mubit inference key for that project, then configure:

```dotenv
ROBO_MEDIC_PROVIDER=mubit
MUBIT_API_FORMAT=openai
MUBIT_BASE_URL=https://api.mubit.ai/compat/openrouter/v1
MUBIT_MODEL=deepseek/deepseek-v4.1-flash-1017
MUBIT_API_KEY=<your Mubit inference key>
```

Change all format/base/model settings together. The OpenRouter key belongs in
Mubit for this route; the app sends its Mubit key. A successful response must
include Mubit's gateway request reference. Saved records retain `provider_kind=mubit`.
Changing the provider/model/format creates a different task from the original
Gemini classifier; set the corresponding management task ID separately.

Mubit currently records these calls and may collect training examples, but its
adapters do not answer OpenRouter calls. Training and serving are separate capabilities.
See the [official Mubit guide](https://docs.mubit.ai/guides/openai-compatible).

## Verify

Start with one synthetic development case. Confirm the provider, model, raw
label, and request reference in the app. No model retries or provider fallbacks
are automatic. A missing key, insufficient credit, unsupported model, timeout,
or malformed reply stays visible. Direct and Mubit records are labelled separately
in history and evaluation. See [OpenRouter API documentation](https://openrouter.ai/docs/quickstart).
