#include "hal/mock/MockTransport.h"

#include <cstdio>
#include <cstring>

#ifndef _WIN32
#include <arpa/inet.h>
#include <netdb.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

namespace sim {

MockTransport::MockTransport() = default;

bool MockTransport::wifiConnect() { return wifi_online_; }

hal::HttpResponse MockTransport::httpGet(const std::string& url) {
  if (!wifi_online_) return {0, {}};
  if (!live_http_base_.empty() && url.rfind(live_http_base_, 0) == 0) {
    return liveGet(url);
  }
  auto it = canned_.find(url);
  if (it != canned_.end()) return it->second;
  return {404, {}};
}

bool MockTransport::mqttConnect() { return mqtt_online_; }

void MockTransport::mqttSubscribe(const std::string& topic, MqttCallback cb) {
  subs_[topic].push_back(cb);
  // Deliver retained message to this subscriber if present.
  auto it = retained_.find(topic);
  if (it != retained_.end()) cb(topic, it->second);
}

void MockTransport::mqttPublish(const std::string& topic,
                                const std::string& payload,
                                bool retained) {
  Publish p{topic, payload, retained};
  publishes_.push_back(p);
  if (retained) retained_[topic] = payload;
  auto it = subs_.find(topic);
  if (it != subs_.end()) {
    for (auto& cb : it->second) cb(topic, payload);
  }
  // Fire the scenario hook last so a scenario that reacts by publishing
  // (e.g., HA-simulation) doesn't recurse on its own publish unexpectedly —
  // by this point `publishes_` and `retained_` are consistent with the
  // original publish.
  if (publish_hook_) publish_hook_(p);
}

std::string MockTransport::mqttReadRetained(const std::string& topic) {
  auto it = retained_.find(topic);
  return it == retained_.end() ? std::string{} : it->second;
}

std::string MockTransport::mqttWaitForMessage(const std::string& topic,
                                              int timeout_ms) {
  // The mock has no real event loop; all scenario-driven HA responses have
  // already fired via the publish hook by the time this is called. Return
  // whichever retained value is present now. timeout_ms is intentionally
  // ignored — real-device semantics live in RealTransport.
  (void)timeout_ms;
  auto it = retained_.find(topic);
  return it == retained_.end() ? std::string{} : it->second;
}

void MockTransport::setRendererResponse(const std::string& url,
                                        std::vector<uint8_t> body,
                                        int status) {
  hal::HttpResponse r;
  r.status = status;
  r.body = std::move(body);
  canned_[url] = std::move(r);
}

std::vector<MockTransport::Publish> MockTransport::publishesOn(
    const std::string& topic) const {
  std::vector<Publish> out;
  for (const auto& p : publishes_) {
    if (p.topic == topic) out.push_back(p);
  }
  return out;
}

// --- live HTTP (dry-run) -----------------------------------------------------

hal::HttpResponse MockTransport::liveGet(const std::string& url) {
#ifndef _WIN32
  // Extract host:port/path from `http://host:port/path`
  const std::string prefix = "http://";
  if (url.rfind(prefix, 0) != 0) return {0, {}};
  std::string rest = url.substr(prefix.size());
  auto slash = rest.find('/');
  std::string hostport = slash == std::string::npos ? rest : rest.substr(0, slash);
  std::string path = slash == std::string::npos ? "/" : rest.substr(slash);
  auto colon = hostport.find(':');
  std::string host = colon == std::string::npos ? hostport : hostport.substr(0, colon);
  int port = colon == std::string::npos ? 80 : std::atoi(hostport.substr(colon + 1).c_str());

  addrinfo hints{};
  hints.ai_family = AF_INET;
  hints.ai_socktype = SOCK_STREAM;
  addrinfo* res = nullptr;
  char port_str[8];
  std::snprintf(port_str, sizeof(port_str), "%d", port);
  if (getaddrinfo(host.c_str(), port_str, &hints, &res) != 0 || !res) return {0, {}};

  int fd = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
  if (fd < 0) { freeaddrinfo(res); return {0, {}}; }
  if (connect(fd, res->ai_addr, res->ai_addrlen) != 0) {
    close(fd); freeaddrinfo(res); return {0, {}};
  }
  freeaddrinfo(res);

  std::string req = "GET " + path + " HTTP/1.0\r\nHost: " + host + "\r\n\r\n";
  ::send(fd, req.data(), req.size(), 0);

  std::vector<uint8_t> buf;
  uint8_t chunk[4096];
  ssize_t n;
  while ((n = ::recv(fd, chunk, sizeof(chunk), 0)) > 0) {
    buf.insert(buf.end(), chunk, chunk + n);
  }
  close(fd);

  // Strip HTTP headers (find \r\n\r\n)
  hal::HttpResponse out;
  const uint8_t sep[] = {'\r', '\n', '\r', '\n'};
  for (std::size_t i = 0; i + 3 < buf.size(); ++i) {
    if (std::memcmp(&buf[i], sep, 4) == 0) {
      std::string status_line(reinterpret_cast<char*>(buf.data()),
                              std::min<std::size_t>(buf.size(), 32));
      int status = 0;
      std::sscanf(status_line.c_str(), "HTTP/%*s %d", &status);
      out.status = status;
      out.body.assign(buf.begin() + static_cast<std::ptrdiff_t>(i + 4), buf.end());
      return out;
    }
  }
  return {0, {}};
#else
  (void)url;
  return {0, {}};
#endif
}

}  // namespace sim
