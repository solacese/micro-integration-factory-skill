# MI test kit

This ZIP belongs to the generated Java MDK and Go alternatives. Use either runtime, one shared YAML, and these tests. SDKPerf binaries are not redistributed.

## Start

Unzip your chosen MI and run its `./scripts/install.sh --demo`. Then unzip this test kit and run:

```bash
./test.sh verify --project ../YOUR-MI-DIRECTORY
./test.sh smoke --project ../YOUR-MI-DIRECTORY --demo
./test.sh samples --project ../YOUR-MI-DIRECTORY --demo
./test.sh performance --project ../YOUR-MI-DIRECTORY --demo
```

Python 3 and Docker are required. The launcher installs its pinned YAML reader into a local .venv. `verify` executes every generated core example, including invalid inputs. `smoke` checks actual broker output bytes and expected topics. `samples` checks HTTP responses and, for Stripe, rejects unsigned requests before sending signed examples. `performance` reproduces the correlation/byte/topic-checked load test, default 1,000 inputs/s for ten measured seconds after ten seconds warmup. A 2% overdrive margin accounts for tail drain; results must actually meet the target with zero errors, duplicates or missing outputs. Results and per-event latency CSV go in results/.

Repeat against the other MI directory after stopping the first. The shared config is included as config/mi-config.yaml; use `--config /path/to/completed/mi-config.yaml` for your broker. The local demo reads the selected project's config/mi-demo.yaml. Override --url for a remote HTTP ingress, --network for a custom Docker network, or --transport smf for a broker that only exposes SMF. With --project, SDKPerf runs in a temporary Java container on the MI's network and uses the same config, so the demo needs no exposed broker ports or host Java. Without --project, SDKPerf runs on the host and its SMF address must be host-reachable. Keep completed credentials private.

## SDK Perf

Install **SDKPerf JCSMP** from [Solace downloads](https://solace.com/downloads/), with a compatible Java runtime. Set --sdkperf to its sdkperf_java.sh launcher. In separate terminals:

```bash
./test.sh sdkperf-subscribe --project ../YOUR-MI-DIRECTORY --demo --sdkperf /path/to/sdkperf_java.sh --seconds 60
./test.sh sdkperf-publish --project ../YOUR-MI-DIRECTORY --demo --sdkperf /path/to/sdkperf_java.sh --rate 1000 --seconds 30
```

SDKPerf publishes the first valid generated fixture as an unchanged binary attachment and subscribes to its expected output topics. Passwords use a temporary mode-600 password file, not command-line values. Other logs may include SDKPerf connection metadata; keep results private. Do not add -l, -oc or -crc to payloads that must remain valid JSON/XML/Avro/Protobuf: these options can add test data to messages. Use the supplied correlated performance runner for MI latency, exact payload and all-route verification. SDKPerf traffic/ACK counters alone do not establish MI processing performance.

**Stripe/webhooks:** broker ingress is deliberately disabled. Use `performance` for signed HTTP input, with `sdkperf-subscribe` in another terminal to observe Solace output. `sdkperf-publish` refuses this flow so it cannot bypass signature verification.

[Official SDKPerf options](https://docs.solace.com/API/SDKPerf/Command-Line-Options.htm) · Use SDKPerf `-hm` to check the installed version's full options, including -pal and -cpf.

## Contents and evidence

- core-examples.json and decoded valid/invalid fixtures: inputs, expected output bytes, properties and topic routes generated for this MI.
- generated-tests/: the matching Java and Go contract, transport and broker test sources. Run them through the chosen complete MI project using verify/smoke above.
- performance/: the reproducible benchmark source and Docker build.
- reports/: the hosted Java/Go performance report and per-event CSV, included after both qualify.
- test-manifest.json: generation metadata and available checks. CLI packaging without --validate includes no passing hosted results.

The default --demo workflow uses synthetic fixtures and an isolated broker. Custom config/URL options target the broker and MI you specify. They do not test your live Stripe/Salesforce account, maximum capacity, long-term stability, atomic fan-out or exactly-once delivery. Complete vendor configuration and rerun tests after changing the core or credentials.
