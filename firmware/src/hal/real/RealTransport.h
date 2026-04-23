#pragma once
#ifdef ARDUINO

#include <Arduino.h>
#include <HTTPClient.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <WiFiClient.h>

#include <string>

#include "hal/ITransport.h"
#include "secrets.h"

namespace fw::hal_real {

// Singleton-ish: PubSubClient needs a free-function/static callback. We stash
// the latest instance here so the trampoline can forward into it.
class RealTransport;
static RealTransport* g_rt_instance = nullptr;

class RealTransport : public hal::ITransport {
 public:
  RealTransport() {
    g_rt_instance = this;
    mqtt_.setClient(client_);
    mqtt_.setServer(INKPLATE_MQTT_HOST, INKPLATE_MQTT_PORT);
    mqtt_.setBufferSize(512);
    mqtt_.setCallback(&RealTransport::trampoline);
  }

  bool wifiConnect() override {
    if (WiFi.status() == WL_CONNECTED) return true;
    WiFi.mode(WIFI_STA);
    WiFi.begin(INKPLATE_WIFI_SSID, INKPLATE_WIFI_PASSWORD);
    uint32_t start = millis();
    while (WiFi.status() != WL_CONNECTED && (millis() - start) < 10000) {
      delay(100);
    }
    return WiFi.status() == WL_CONNECTED;
  }

  hal::HttpResponse httpGet(const std::string& url) override {
    hal::HttpResponse r;
    HTTPClient http;
    http.begin(url.c_str());
    http.setTimeout(3000);
    int code = http.GET();
    r.status = code;
    if (code > 0) {
      int len = http.getSize();
      if (len > 0) r.body.reserve(static_cast<size_t>(len));
      WiFiClient* stream = http.getStreamPtr();
      uint8_t buf[512];
      while (http.connected() && (len > 0 || len == -1)) {
        size_t avail = stream->available();
        if (avail) {
          int got = stream->readBytes(buf, avail > sizeof(buf) ? sizeof(buf) : avail);
          r.body.insert(r.body.end(), buf, buf + got);
          if (len > 0) len -= got;
        } else {
          delay(1);
        }
      }
    }
    http.end();
    return r;
  }

  bool mqttConnect() override {
    if (mqtt_.connected()) return true;
    return mqtt_.connect(INKPLATE_DEVICE_ID, INKPLATE_MQTT_USER, INKPLATE_MQTT_PASS);
  }

  // Not used by the current main loop (retained reads use mqttReadRetained).
  // If a future handler needs live subscriptions, store `cb` in a map keyed by
  // topic and fan out in `trampoline`.
  void mqttSubscribe(const std::string& topic, MqttCallback /*cb*/) override {
    mqtt_.subscribe(topic.c_str());
  }

  void mqttPublish(const std::string& topic,
                   const std::string& payload,
                   bool retained) override {
    mqtt_.publish(topic.c_str(),
                  reinterpret_cast<const uint8_t*>(payload.data()),
                  payload.size(), retained);
    // Flush in-flight PUBLISH packets before the caller proceeds or sleeps.
    mqtt_.loop();
  }

  // Subscribe to `topic` at QoS 0 and spin the MQTT event loop briefly to
  // catch the retained payload the broker replays. Returns the payload as a
  // std::string; empty if nothing arrived within the timeout.
  std::string mqttReadRetained(const std::string& topic) override {
    return waitImpl(topic, 800);  // typical retained-replay latency <50ms
  }

  // Subscribe to `topic` at QoS 0, spin the event loop for up to timeout_ms,
  // and return the most recently received payload (retained or push). Used
  // by the post-gesture grace window so HA has time to process the tap and
  // re-publish active_mode.
  std::string mqttWaitForMessage(const std::string& topic, int timeout_ms) override {
    return waitImpl(topic, timeout_ms);
  }

 private:
  std::string waitImpl(const std::string& topic, int timeout_ms) {
    captured_topic_ = topic;
    captured_payload_.clear();
    captured_ = false;

    mqtt_.subscribe(topic.c_str(), /*qos=*/0);

    uint32_t deadline = millis() + static_cast<uint32_t>(timeout_ms);
    while (millis() < deadline && !captured_) {
      mqtt_.loop();
      delay(5);
    }

    mqtt_.unsubscribe(topic.c_str());
    return captured_payload_;
  }

  WiFiClient   client_;
  PubSubClient mqtt_;

  std::string  captured_topic_;
  std::string  captured_payload_;
  bool         captured_ = false;

  static void trampoline(char* topic, uint8_t* payload, unsigned int len) {
    if (!g_rt_instance) return;
    if (g_rt_instance->captured_topic_ != topic) return;
    g_rt_instance->captured_payload_.assign(reinterpret_cast<const char*>(payload),
                                            static_cast<size_t>(len));
    g_rt_instance->captured_ = true;
  }
};

}  // namespace fw::hal_real

#endif  // ARDUINO
