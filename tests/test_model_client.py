import json
import os
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

from llm_gym.agent.model_client import (AnthropicClient, ModelProviderError,
                                    OpenAICompatibleClient, model_client_from_environment)


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def close(self):
        return None


def http_400_opener(request, timeout):
    raise HTTPError(request.full_url, 400, "Bad Request", {}, Response({
        "error": {"type": "invalid_request_error", "message": "model not found"}
    }))


class ModelClientTests(unittest.TestCase):
    def test_client_sends_provider_request_without_exposing_key_in_payload(self):
        requests = []

        def opener(request, timeout):
            requests.append((request, timeout))
            return Response({"choices": [{"message": {"content": '{"answer":"ok","classification":"SUPPORTED","citation_ids":["e1"]}'}}]})

        result = OpenAICompatibleClient(api_key="secret", base_url="https://provider.test/v1", opener=opener, timeout_seconds=4).complete(
            system="system", user="user", model="model", max_output_tokens=10)
        self.assertIn('"answer"', result)
        self.assertNotIn("secret", requests[0][0].data.decode("utf-8"))
        self.assertEqual(requests[0][1], 4)

    def test_openai_client_records_usage_and_request_timeout(self):
        requests = []

        def opener(request, timeout):
            requests.append((request, timeout))
            return Response({"usage": {"prompt_tokens": 1000, "completion_tokens": 500},
                             "choices": [{"message": {"content": '{"answer":"ok"}'}}]})

        with patch.dict(os.environ, {"AGENT_INPUT_COST_PER_MILLION": "1", "AGENT_OUTPUT_COST_PER_MILLION": "2"}):
            client = OpenAICompatibleClient(api_key="secret", base_url="https://provider.test/v1",
                                            opener=opener, timeout_seconds=4)
            client.complete(system="system", user="user", model="model", max_output_tokens=10,
                            timeout_seconds=2)
        self.assertEqual(requests[0][1], 2)
        self.assertEqual(client.last_usage["input_tokens"], 1000)
        self.assertEqual(client.last_usage["cost_usd"], 0.002)

    def test_anthropic_client_uses_messages_api_headers_and_shape(self):
        requests = []

        def opener(request, timeout):
            requests.append(request)
            return Response({"content": [{"type": "text", "text": '{"answer":"ok","classification":"SUPPORTED","citation_ids":["e1"]}'}]})

        result = AnthropicClient(api_key="secret", base_url="https://provider.test",
                                 opener=opener).complete(system="system", user="user",
                                                         model="claude-sonnet", max_output_tokens=10)
        self.assertIn('"answer"', result)
        self.assertEqual(requests[0].full_url, "https://provider.test/v1/messages")
        self.assertEqual(requests[0].get_header("X-api-key"), "secret")
        self.assertEqual(requests[0].get_header("Anthropic-version"), "2023-06-01")
        body = json.loads(requests[0].data.decode("utf-8"))
        self.assertEqual(body["messages"], [{"role": "user", "content": "user"}])
        self.assertEqual(body["system"], "system")
        self.assertEqual(body["thinking"], {"type": "disabled"})
        self.assertNotIn("temperature", body)

    def test_anthropic_client_extracts_text_after_thinking_block(self):
        def opener(request, timeout):
            return Response({
                "content": [
                    {"type": "thinking", "thinking": "inspect the evidence"},
                    {"type": "text", "text": '{"answer":"ok"}'},
                ]
            })

        result = AnthropicClient(api_key="secret", base_url="https://provider.test",
                                 opener=opener).complete(
                                     system="system", user="user", model="claude-sonnet-5",
                                     max_output_tokens=10)
        self.assertEqual(result, '{"answer":"ok"}')

    def test_provider_factory_selects_anthropic(self):
        with patch.dict(os.environ, {"AGENT_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "secret"}, clear=False):
            self.assertIsInstance(model_client_from_environment(opener=lambda *_: None), AnthropicClient)

    def test_provider_factory_supports_separate_comparison_prefix(self):
        with patch.dict(os.environ, {"FRONTIER_PROVIDER": "anthropic", "FRONTIER_API_KEY": "secret"}, clear=False):
            self.assertIsInstance(model_client_from_environment(prefix="FRONTIER", opener=lambda *_: None), AnthropicClient)

    def test_http_400_preserves_provider_diagnostic_and_is_not_retryable(self):
        client = AnthropicClient(api_key="secret", base_url="https://provider.test",
                                 opener=http_400_opener)
        with self.assertRaisesRegex(ModelProviderError, r"HTTP 400: model not found") as raised:
            client.complete(system="system", user="user", model="claude-sonnet-5", max_output_tokens=10)
        self.assertFalse(raised.exception.retryable)

    def test_a_failed_request_clears_usage_from_the_previous_request(self):
        calls = 0

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                return Response({
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                    "choices": [{"message": {"content": '{"answer":"ok"}'}}],
                })
            raise HTTPError(request.full_url, 500, "Unavailable", {}, Response({
                "error": {"message": "temporary outage"}
            }))

        client = OpenAICompatibleClient(
            api_key="secret", base_url="https://provider.test/v1", opener=opener)
        client.complete(system="s", user="u", model="m", max_output_tokens=10)
        self.assertEqual(client.last_usage["input_tokens"], 10)
        with self.assertRaises(ModelProviderError):
            client.complete(system="s", user="u", model="m", max_output_tokens=10)
        self.assertEqual(client.last_usage, {})


class ProviderRequestShapeTests(unittest.TestCase):
    """An OpenAI-compatible URL does not imply an OpenAI-compatible body.

    GLM-5.2 is reached through /chat/completions but does not document
    response_format, and enables reasoning by default at max effort — which
    bills as output and can consume the whole token budget before any JSON is
    emitted. Both fields therefore have to be configurable per provider.
    """

    def _sent_body(self, client):
        captured = {}

        def opener(request, timeout):
            captured.update(json.loads(request.data.decode("utf-8")))
            return Response({"choices": [{"message": {"content": '{"answer":"ok"}'}}]})

        client.opener = opener
        client.complete(system="s", user="u", model="m", max_output_tokens=10)
        return captured

    def test_default_openai_body_is_unchanged(self):
        with patch.dict(os.environ, {}, clear=True):
            client = OpenAICompatibleClient(api_key="k", base_url="https://p.test/v1")
        body = self._sent_body(client)
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertNotIn("thinking", body)

    def test_glm_shape_omits_response_format_and_disables_reasoning(self):
        client = OpenAICompatibleClient(api_key="k", base_url="https://api.z.ai/api/paas/v4",
                                        response_format="none", thinking="disabled")
        body = self._sent_body(client)
        self.assertNotIn("response_format", body)
        self.assertEqual(body["thinking"], {"type": "disabled"})
        # The rest of the contract must not drift while accommodating a provider.
        self.assertEqual(body["temperature"], 0)
        self.assertEqual(body["max_tokens"], 10)

    def test_options_are_read_per_provider_prefix(self):
        """Each comparison arm configures its own body shape independently."""
        with patch.dict(os.environ, {
            "OPEN_WEIGHT_PROVIDER": "openai-compatible",
            "OPEN_WEIGHT_API_KEY": "k",
            "OPEN_WEIGHT_BASE_URL": "https://api.z.ai/api/paas/v4",
            "OPEN_WEIGHT_RESPONSE_FORMAT": "none",
            "OPEN_WEIGHT_THINKING": "disabled",
            "AGENT_API_KEY": "k2",
        }, clear=True):
            open_weight = model_client_from_environment(prefix="OPEN_WEIGHT")
            agent = model_client_from_environment(prefix="AGENT")
        self.assertNotIn("response_format", self._sent_body(open_weight))
        self.assertEqual(self._sent_body(agent)["response_format"], {"type": "json_object"})

    def test_anthropic_still_disables_thinking_by_default(self):
        captured = {}

        def opener(request, timeout):
            captured.update(json.loads(request.data.decode("utf-8")))
            return Response({"content": [{"type": "text", "text": '{"answer":"ok"}'}]})

        with patch.dict(os.environ, {}, clear=True):
            client = AnthropicClient(api_key="k", base_url="https://p.test", opener=opener)
        client.complete(system="s", user="u", model="m", max_output_tokens=10)
        self.assertEqual(captured["thinking"], {"type": "disabled"})

    def test_thinking_can_be_omitted_entirely(self):
        """A provider that rejects an unknown field needs it absent, not false."""
        captured = {}

        def opener(request, timeout):
            captured.update(json.loads(request.data.decode("utf-8")))
            return Response({"content": [{"type": "text", "text": '{"answer":"ok"}'}]})

        client = AnthropicClient(api_key="k", base_url="https://p.test", opener=opener,
                                 thinking="none")
        client.complete(system="s", user="u", model="m", max_output_tokens=10)
        self.assertNotIn("thinking", captured)

    def test_an_unusable_option_fails_at_construction_naming_the_variable(self):
        with patch.dict(os.environ, {"OPEN_WEIGHT_THINKING": "disable"}, clear=True):
            with self.assertRaisesRegex(ValueError, "OPEN_WEIGHT_THINKING"):
                OpenAICompatibleClient(api_key="k", base_url="https://p.test/v1",
                                       cost_prefix="OPEN_WEIGHT")
        with patch.dict(os.environ, {"AGENT_RESPONSE_FORMAT": "json"}, clear=True):
            with self.assertRaisesRegex(ValueError, "AGENT_RESPONSE_FORMAT"):
                OpenAICompatibleClient(api_key="k", base_url="https://p.test/v1")


class TruncationDetectionTests(unittest.TestCase):
    """A truncated response must report truncation, not a JSON parse failure.

    Live symptom this guards: an over-long answer was cut at max_output_tokens,
    producing invalid JSON, which surfaced downstream as "model response must be
    valid JSON" and pointed the reader at the wrong cause.
    """

    def test_anthropic_reports_truncation_rather_than_bad_json(self):
        def opener(request, timeout):
            return Response({
                "content": [{"type": "text", "text": '{ "answer": "cut off mid-sen'}],
                "stop_reason": "max_tokens",
                "usage": {"input_tokens": 100, "output_tokens": 50},
            })
        client = AnthropicClient(api_key="secret", base_url="https://provider.test",
                                 opener=opener)
        with self.assertRaisesRegex(ModelProviderError, "truncated at max_output_tokens=2000") as raised:
            client.complete(system="s", user="u", model="claude-sonnet-5",
                            max_output_tokens=2000)
        self.assertFalse(raised.exception.retryable)
        self.assertEqual(client.last_usage["input_tokens"], 100)
        self.assertEqual(client.last_usage["output_tokens"], 50)

    def test_openai_compatible_reports_truncation(self):
        def opener(request, timeout):
            return Response({"usage": {"prompt_tokens": 120, "completion_tokens": 60},
                             "choices": [{
                "message": {"content": '{ "answer": "cut off'},
                "finish_reason": "length",
            }]})
        client = OpenAICompatibleClient(api_key="secret", base_url="https://provider.test/v1",
                                        opener=opener)
        with self.assertRaisesRegex(ModelProviderError, "truncated at max_output_tokens=1500"):
            client.complete(system="s", user="u", model="m", max_output_tokens=1500)
        self.assertEqual(client.last_usage["input_tokens"], 120)
        self.assertEqual(client.last_usage["output_tokens"], 60)

    def test_empty_openai_truncation_is_not_misreported_as_empty_content(self):
        def opener(request, timeout):
            return Response({"choices": [{
                "message": {"content": ""}, "finish_reason": "length",
            }]})
        client = OpenAICompatibleClient(
            api_key="secret", base_url="https://provider.test/v1", opener=opener)
        with self.assertRaisesRegex(ModelProviderError, "truncated at max_output_tokens=99"):
            client.complete(system="s", user="u", model="m", max_output_tokens=99)

    def test_complete_response_is_not_flagged_as_truncated(self):
        def opener(request, timeout):
            return Response({
                "content": [{"type": "text", "text": '{"answer":"ok"}'}],
                "stop_reason": "end_turn",
            })
        client = AnthropicClient(api_key="secret", base_url="https://provider.test",
                                 opener=opener)
        self.assertEqual(
            client.complete(system="s", user="u", model="m", max_output_tokens=2000),
            '{"answer":"ok"}',
        )


class LatencyMeasurementTests(unittest.TestCase):
    """Per-call latency and throughput, so providers can be compared.

    Raw latency alone is confounded by answer length, so the comparable
    figure is output tokens per second. Both clients block until the whole
    response is read, so the recorded time is time-to-last-token.
    """

    def _clock(self, *ticks):
        return patch("llm_gym.agent.model_client.perf_counter", side_effect=list(ticks))

    def test_openai_client_records_time_to_last_token_and_throughput(self):
        def opener(request, timeout):
            return Response({"usage": {"prompt_tokens": 1000, "completion_tokens": 500},
                             "choices": [{"message": {"content": '{"answer":"ok"}'}}]})

        client = OpenAICompatibleClient(api_key="secret", base_url="https://provider.test/v1",
                                        opener=opener)
        with self._clock(10.0, 14.0):
            client.complete(system="s", user="u", model="m", max_output_tokens=10)
        self.assertEqual(client.last_usage["latency_seconds"], 4.0)
        self.assertEqual(client.last_usage["output_tokens_per_second"], 125.0)

    def test_anthropic_client_records_time_to_last_token_and_throughput(self):
        def opener(request, timeout):
            return Response({"usage": {"input_tokens": 800, "output_tokens": 300},
                             "content": [{"type": "text", "text": '{"answer":"ok"}'}]})

        client = AnthropicClient(api_key="secret", base_url="https://provider.test",
                                 opener=opener)
        with self._clock(100.0, 102.5):
            client.complete(system="s", user="u", model="m", max_output_tokens=10)
        self.assertEqual(client.last_usage["latency_seconds"], 2.5)
        self.assertEqual(client.last_usage["output_tokens_per_second"], 120.0)

    def test_a_clock_too_coarse_to_measure_reports_no_throughput(self):
        """Never divide by zero, and never report a fabricated rate instead."""
        def opener(request, timeout):
            return Response({"usage": {"prompt_tokens": 10, "completion_tokens": 5},
                             "choices": [{"message": {"content": '{"answer":"ok"}'}}]})

        client = OpenAICompatibleClient(api_key="secret", base_url="https://provider.test/v1",
                                        opener=opener)
        with self._clock(7.0, 7.0):
            client.complete(system="s", user="u", model="m", max_output_tokens=10)
        self.assertEqual(client.last_usage["latency_seconds"], 0.0)
        self.assertIsNone(client.last_usage["output_tokens_per_second"])
