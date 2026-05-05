#pragma once

#include <functional>
#include <map>
#include <string>
#include <unordered_map>
#include <vector>

#include "hal/ITransport.h"
#include "hal/types.h"

namespace sim {

// Mock WiFi + HTTP + MQTT. Good enough for scenarios, not a full broker.
//
// HTTP: responses scripted by URL. Unscripted URLs return status 0 (offline)
// when wifi is off, or 404 when wifi is on.
// MQTT: retained messages keyed by topic; subscribers get the retained payload
// immediately on subscribe; publish notifies all subscribers to a matching
// topic (exact match — no wildcard support). Dry-run mode swaps the HTTP stub
// for a live client hitting a configured host:port.
//
// Grace-window simulation: scenarios can install a publish-hook via
// `setPublishHook()`. The hook fires synchronously inside `mqttPublish`,
// letting a test react to a device-side publish by e.g. publishing the
// gesture_response event — which then becomes visible to the subsequent
// `mqttWaitForMessage` call. This models HA's response inside the device's
// grace window without needing real event-loop timing. `mqttWaitForMessage`
// returns either the retained value (mimics broker replay on subscribe) or
// the most recent non-retained push since the last drain, draining the push
// buffer on read so a second wait without a fresh push returns empty.
class MockTransport : public hal::ITransport {
 public:
  struct Publish {
    std::string topic;
    std::string payload;
    bool retained;
  };
  using PublishHook = std::function<void(const Publish&)>;

  MockTransport();

  bool wifiConnect() override;
  hal::HttpResponse httpGet(const std::string& url) override;
  bool mqttConnect() override;
  void mqttSubscribe(const std::string& topic, MqttCallback cb) override;
  void mqttPublish(const std::string& topic,
                   const std::string& payload,
                   bool retained) override;
  std::string mqttReadRetained(const std::string& topic) override;
  std::string mqttWaitForMessage(const std::string& topic,
                                 int timeout_ms) override;

  // Test-facing API
  void setWifiOnline(bool b) { wifi_online_ = b; }
  void setMqttOnline(bool b) { mqtt_online_ = b; }
  void setRendererResponse(const std::string& url, std::vector<uint8_t> body,
                           int status = 200);
  // Scenario-side HA simulation: the hook is invoked synchronously inside
  // every call to mqttPublish. Use to react to device publishes (e.g.,
  // state/gesture) by publishing the corresponding retained command topic.
  void setPublishHook(PublishHook hook) { publish_hook_ = std::move(hook); }

  // Drop a retained message — simulates a broker-delivery miss (e.g., the
  // 800 ms `mqttReadRetained` window expiring before the broker re-delivered
  // on a marginal-RSSI link). Subsequent reads return empty until the topic
  // is re-published.
  void clearRetained(const std::string& topic) { retained_.erase(topic); }

  // Dry-run: forward HTTP GETs to a real host:port (default empty = disabled).
  void setLiveHttpBase(std::string base) { live_http_base_ = std::move(base); }

  const std::vector<Publish>& publishes() const { return publishes_; }
  std::vector<Publish> publishesOn(const std::string& topic) const;

 private:
  bool wifi_online_ = true;
  bool mqtt_online_ = true;
  std::unordered_map<std::string, hal::HttpResponse> canned_;
  std::map<std::string, std::string> retained_;  // retained msgs by topic
  std::map<std::string, std::string> pending_push_;  // last non-retained push per topic, drained by mqttWaitForMessage
  std::map<std::string, std::vector<MqttCallback>> subs_;
  std::vector<Publish> publishes_;
  PublishHook publish_hook_;
  std::string live_http_base_;

  hal::HttpResponse liveGet(const std::string& url);
};

}  // namespace sim
