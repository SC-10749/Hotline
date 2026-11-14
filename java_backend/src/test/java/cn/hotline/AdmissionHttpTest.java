package cn.hotline;

import com.fasterxml.jackson.databind.JsonNode;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {"spring.cloud.nacos.discovery.enabled=false", "hotline.python.mode=static",
                "hotline.admission.store=memory"})
class AdmissionHttpTest {

    private static final HttpServer UPSTREAM = upstream();

    @Autowired
    private TestRestTemplate http;

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("hotline.python.base-url", () -> "http://127.0.0.1:" + UPSTREAM.getAddress().getPort());
    }

    private static HttpServer upstream() {
        try {
            HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/health", exchange -> {
                byte[] body = "{\"status\":\"UP\",\"service\":\"hotline-agent\"}".getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set("Content-Type", "application/json");
                exchange.sendResponseHeaders(200, body.length);
                try (var output = exchange.getResponseBody()) {
                    output.write(body);
                }
            });
            server.start();
            return server;
        } catch (IOException exception) {
            throw new IllegalStateException(exception);
        }
    }

    @AfterAll
    static void stop() {
        UPSTREAM.stop(0);
    }

    @Test
    void blacklistedClientIsDeniedAndRestoredAfterRemoval() {
        ResponseEntity<JsonNode> added = http.postForEntity("/api/v1/admission/blacklist",
                Map.of("entry", "user:blocked-1"), JsonNode.class);
        assertThat(added.getStatusCode().value()).isEqualTo(200);
        assertThat(added.getBody().path("success").asBoolean()).isTrue();

        ResponseEntity<JsonNode> denied = getWithUser("blocked-1");
        assertThat(denied.getStatusCode().value()).isEqualTo(403);
        assertThat(denied.getBody().path("code").asText()).isEqualTo("FORBIDDEN");

        ResponseEntity<JsonNode> removed = removeBlacklistEntry("user:blocked-1");
        assertThat(removed.getBody().path("success").asBoolean()).isTrue();

        assertThat(getWithUser("blocked-1").getStatusCode().value()).isEqualTo(200);
    }

    @Test
    void blacklistByRemoteAddressBlocksRequestsWithoutHeader() {
        http.postForEntity("/api/v1/admission/blacklist", Map.of("entry", "ip:127.0.0.1"), JsonNode.class);
        try {
            ResponseEntity<JsonNode> denied = http.getForEntity("/api/v1/capabilities/python/health", JsonNode.class);
            assertThat(denied.getStatusCode().value()).isEqualTo(403);
        } finally {
            removeBlacklistEntry("ip:127.0.0.1");
        }
    }

    @Test
    void statusExposesStoreAndSortedBlacklist() {
        http.postForEntity("/api/v1/admission/blacklist", Map.of("entry", "user:zeta"), JsonNode.class);
        http.postForEntity("/api/v1/admission/blacklist", Map.of("entry", "ip:10.9.9.9"), JsonNode.class);
        try {
            ResponseEntity<JsonNode> status = http.getForEntity("/api/v1/admission/status", JsonNode.class);
            assertThat(status.getStatusCode().value()).isEqualTo(200);
            assertThat(status.getBody().path("store").asText()).isEqualTo("InMemoryAdmissionStore");

            List<String> blacklist = new ArrayList<>();
            status.getBody().path("blacklist").forEach(node -> blacklist.add(node.asText()));
            assertThat(blacklist).contains("user:zeta", "ip:10.9.9.9");
            assertThat(blacklist.indexOf("ip:10.9.9.9")).isLessThan(blacklist.indexOf("user:zeta"));
        } finally {
            removeBlacklistEntry("user:zeta");
            removeBlacklistEntry("ip:10.9.9.9");
        }
    }

    @Test
    void invalidBlacklistEntryIsRejected() {
        ResponseEntity<JsonNode> response = http.postForEntity("/api/v1/admission/blacklist",
                Map.of("entry", "not-a-key"), JsonNode.class);
        assertThat(response.getStatusCode().value()).isEqualTo(400);
        assertThat(response.getBody().path("code").asText()).isEqualTo("INVALID_ARGUMENT");
    }

    @Test
    void removingUnknownEntryReportsFailure() {
        ResponseEntity<JsonNode> response = removeBlacklistEntry("user:nobody");
        assertThat(response.getStatusCode().value()).isEqualTo(200);
        assertThat(response.getBody().path("success").asBoolean()).isFalse();
    }

    private ResponseEntity<JsonNode> getWithUser(String user) {
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-Hotline-User", user);
        return http.exchange("/api/v1/capabilities/python/health", HttpMethod.GET,
                new HttpEntity<>(headers), JsonNode.class);
    }

    private ResponseEntity<JsonNode> removeBlacklistEntry(String entry) {
        return http.exchange("/api/v1/admission/blacklist?entry=" + entry, HttpMethod.DELETE, null, JsonNode.class);
    }
}
