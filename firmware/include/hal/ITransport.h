#pragma once

#include <functional>
#include <string>

#include "hal/types.h"

namespace hal {

// ITransport — WiFi + HTTP + MQTT abstracted as a single interface.
//
// Grouping rationale: the real implementation needs coordinated init
// (bring up WiFi before HTTP/MQTT), and scenarios toggle online/offline
// state for the whole stack at once. Splitting across three interfaces
// required every scenario to set each one individually; in practice
// they always move together.
//
// Contract:
//   * `wifiConnect()` blocks until connected or times out. Returns true on
//     success. Subsequent calls while connected are no-ops.
//   * `httpGet(url)` returns an HttpResponse. Non-200 responses propagate
//     status + body; transport-level failures throw (device) / set
//     status=0 (mock).
//   * `mqttConnect()` connects to the configured broker (blocks ≤5 s).
//   * `mqttSubscribe(topic)` subscribes with QoS 0. `cb` is invoked for each
//     incoming message. Implementations may coalesce retained messages.
//   * `mqttPublish(topic, payload, retained)` publishes with QoS 0. Retained
//     flag controls whether the broker stores the message for late subscribers.
//   * `mqttReadRetained(topic)` performs a one-shot read of the retained
//     payload on a topic by subscribing, waiting for the retained message
//     (≤500 ms), and unsubscribing. Empty result means "no retained message".
//   * `mqttWaitForMessage(topic, timeout_ms)` subscribes to `topic`, spins
//     the MQTT event loop for up to `timeout_ms`, and returns the payload
//     of the most recently received message (including a retained replay).
//     Used by the IMU-wake grace window so HA has a chance to process the
//     just-published gesture and re-publish `active_mode` before the device
//     commits to fetching a face. Empty result means nothing was received
//     within the window.
//
// Lifecycle:
//   Construct once per boot; all connect calls are explicit from firmware.
class ITransport {
 public:
  using MqttCallback =
      std::function<void(const std::string& topic, const std::string& payload)>;

  virtual ~ITransport() = default;
  virtual bool wifiConnect() = 0;
  virtual HttpResponse httpGet(const std::string& url) = 0;
  virtual bool mqttConnect() = 0;
  virtual void mqttSubscribe(const std::string& topic, MqttCallback cb) = 0;
  virtual void mqttPublish(const std::string& topic,
                           const std::string& payload,
                           bool retained) = 0;
  virtual std::string mqttReadRetained(const std::string& topic) = 0;
  virtual std::string mqttWaitForMessage(const std::string& topic,
                                         int timeout_ms) = 0;
};

}  // namespace hal
