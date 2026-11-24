"""Observe the pinned engine's native threshold and one real local summary on a disposable profile."""
import json
import os
from urllib.parse import urlsplit

import httpx
from agent.context_compressor import ContextCompressor
from agent.model_metadata import estimate_messages_tokens_rough
from hermes_cli.config import load_config

assert os.environ["HERMES_HOME"].endswith("/profiles/stage3b-test")
config = load_config()
model, compression = config["model"], config["compression"]
route = config["auxiliary"]["compression"]
assert config.get("fallback_model") == []
assert route["base_url"] == model["base_url"] == "http://192.168.0.13:8731/v1"
assert route["model"] == model["default"] and route["provider"] == model["provider"] == "custom"
options = dict(model=model["default"], base_url=model["base_url"], provider=model["provider"],
               config_context_length=model["context_length"], threshold_percent=compression["threshold"],
               quiet_mode=True)
normal = ContextCompressor(**options, protect_last_n=compression["protect_last_n"],
                           threshold_tokens_cap=compression["threshold_tokens"])
assert normal.threshold_tokens == 131072
test = ContextCompressor(**options, protect_first_n=1, protect_last_n=3, tail_mode="legacy", threshold_tokens_cap=900)
history = [{"role":"user" if i % 2 == 0 else "assistant",
            "content":f"Synthetic acceptance turn {i}. "
                      + (f"Tray {i} has two quartz samples. The local fixture records both weights and their blue labels. " * 5)}
           for i in range(24)]
estimated = estimate_messages_tokens_rough(history)
assert test.should_compress(estimated)
requests = []
send = httpx.Client.send
async_send = httpx.AsyncClient.send


def observe(request, response):
    if request.url.path.endswith("/chat/completions"):
        requests.append({"path":request.url.path, "model":json.loads(request.content)["model"],
                         "status":response.status_code})


def check(request):
    if urlsplit(str(request.url)).netloc != "192.168.0.13:8731":
        raise AssertionError("Unexpected inference destination")


def traced(client, request, **kwargs):
    check(request)
    response = send(client, request, **kwargs)
    observe(request, response)
    return response


async def traced_async(client, request, **kwargs):
    check(request)
    response = await async_send(client, request, **kwargs)
    observe(request, response)
    return response


httpx.Client.send, httpx.AsyncClient.send = traced, traced_async
try:
    compressed = test.compress(history, current_tokens=estimated)
finally:
    httpx.Client.send, httpx.AsyncClient.send = send, async_send
metrics = test._last_compression_telemetry
fields = ("method","fallback_used","failure_class","aux_provider","aux_model","messages_before","messages_after",
          "tokens_before","tokens_after","tokens_reclaimed","aux_call_duration_ms")
print(json.dumps({"normal_threshold":normal.threshold_tokens,"normal_context":normal.context_length,
                  "test_threshold":test.threshold_tokens,"test_tail":test.protect_last_n,"estimated":estimated,
                  "requests":requests,"metrics":{k:metrics.get(k) for k in fields}}))
assert len(compressed) < len(history) and metrics.get("method") == "llm_summary"
assert not metrics["fallback_used"] and requests and all(r["status"] == 200 and r["model"] == model["default"] for r in requests)
