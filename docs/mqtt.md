# MQTT

Topics use `rafeeq/v1/devices/{device_id}/{status|events|commands|command-results}`. Emergency events and commands use QoS 1 and are deduplicated by UUID. Heartbeats may use QoS 0 or 1. The robot must persist outgoing events before publishing and retain the original UTC `occurred_at` value across retries.

