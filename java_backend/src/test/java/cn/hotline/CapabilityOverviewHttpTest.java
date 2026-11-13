package cn.hotline;

import com.fasterxml.jackson.databind.JsonNode;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {"spring.cloud.nacos.discovery.enabled=false", "hotline.python.mode=static",
                "hotline.admission.store=memory"})
class CapabilityOverviewHttpTest {

    private static final HttpServer UPSTREAM = upstream();
    private static volatile boolean degraded;

    @Autowired
    private TestRestTemplate http;

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("hotline.python.base-url", () -> "http://127.0.0.1:" + UPSTREAM.getAddress().getPort());
    }

    private static HttpServer upstream() {
        try {
            HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/health", exchange -> respond(exchange,
                    "{\"status\":\"UP\",\"service\":\"hotline-agent\",\"version\":\"fastapi\"}"));
            server.createContext("/skill/list", exchange -> respond(exchange,
                    "{\"code\":0,\"message\":\"ok\",\"data\":{\"count\":2,"
                            + "\"skills\":[{\"name\":\"web-search\"},{\"name\":\"code-run\"}]}}"));
            server.createContext("/harness/overview", exchange -> respond(exchange,
                    "{\"agents\":3,\"sessions\":5}"));
            server.start();
            return server;
        } catch (IOException exception) {
            throw new IllegalStateException(exception);
        }
    }

    private static void respond(HttpExchange exchange, String body) throws IOException {
        byte[] bytes = (degraded ? "{\"detail\":\"unavailable\"}" : body).getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.sendResponseHeaders(degraded ? 503 : 200, bytes.length);
        try (var output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    @BeforeEach
    void reset() {
        degraded = false;
    }

    @AfterAll
    static void stop() {
        UPSTREAM.stop(0);
    }

    @Test
    void aggregatesPythonStatusSkillsAndHarness() {
        ResponseEntity<JsonNode> response = http.getForEntity("/api/v1/capabilities/overview", JsonNode.class);

        assertThat(response.getStatusCode().value()).isEqualTo(200);
        JsonNode body = response.getBody();
        assertThat(body.path("generatedAt").asText()).isNotBlank();
        assertThat(body.path("requestId").asText()).isNotBlank();
        assertThat(body.path("python").path("health").path("status").asText()).isEqualTo("UP");
        assertThat(body.path("python").path("health").path("service").asText()).isEqualTo("hotline-agent");
        assertThat(body.path("python").path("readiness").path("status").asText()).isEqualTo("UP");
        assertThat(body.path("skills").path("count").asInt()).isEqualTo(2);
        assertThat(body.path("skills").path("skills")).hasSize(2);
        assertThat(body.path("harness").path("agents").asInt()).isEqualTo(3);
    }

    @Test
    void degradesGracefullyWhenPythonIsUnavailable() {
        degraded = true;

        ResponseEntity<JsonNode> response = http.getForEntity("/api/v1/capabilities/overview", JsonNode.class);

        assertThat(response.getStatusCode().value()).isEqualTo(200);
        JsonNode body = response.getBody();
        assertThat(body.path("python").path("health").path("status").asText()).isEqualTo("UNAVAILABLE");
        assertThat(body.path("python").path("readiness").path("status").asText()).isEqualTo("UNAVAILABLE");
        assertThat(body.path("skills").path("unavailable").asBoolean()).isTrue();
        assertThat(body.path("harness").path("unavailable").asBoolean()).isTrue();
    }
}
