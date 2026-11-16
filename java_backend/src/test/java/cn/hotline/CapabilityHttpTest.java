package cn.hotline;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import com.fasterxml.jackson.databind.JsonNode;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.ResponseEntity;
import org.springframework.core.env.Environment;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {"spring.cloud.nacos.discovery.enabled=false", "hotline.python.mode=static",
                "hotline.admission.store=memory",
                "HOTLINE_NACOS_ENABLED=true", "HOTLINE_NACOS_REGISTER_ENABLED=false"})
class CapabilityHttpTest {
    private static final HttpServer UPSTREAM = upstream();
    private static volatile int healthStatus;
    private static volatile int readinessStatus;
    private static volatile String healthBody;

    @Autowired
    private TestRestTemplate http;

    @Autowired
    private Environment environment;

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("hotline.python.base-url", () -> "http://127.0.0.1:" + UPSTREAM.getAddress().getPort());
    }

    private static HttpServer upstream() {
        try {
            HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/health", exchange -> {
                boolean ready = exchange.getRequestURI().getPath().equals("/health/ready");
                int status = ready ? readinessStatus : healthStatus;
                String body = ready ? "{\"status\":\"UP\",\"service\":\"hotline-agent\"}" : healthBody;
                byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set("Content-Type", "application/json");
                exchange.sendResponseHeaders(status, bytes.length);
                try (var output = exchange.getResponseBody()) {
                    output.write(bytes);
                }
            });
            server.start();
            return server;
        } catch (IOException exception) {
            throw new IllegalStateException(exception);
        }
    }

    @BeforeEach
    void reset() {
        healthStatus = 200;
        readinessStatus = 200;
        healthBody = "{\"status\":\"UP\",\"service\":\"hotline-agent\",\"version\":\"fastapi\"}";
    }

    @AfterAll
    static void stop() {
        UPSTREAM.stop(0);
    }

    @Test
    void callsPythonThroughTheNormalHttpEntryPoint() {
        ResponseEntity<JsonNode> response = http.getForEntity("/api/v1/capabilities/python/health", JsonNode.class);
        assertThat(response.getStatusCode().value()).isEqualTo(200);
        assertThat(response.getBody().path("service").asText()).isEqualTo("hotline-agent");
        assertThat(response.getBody().path("version").asText()).isEqualTo("fastapi");
    }

    @Test
    void readinessAcceptsTheExistingPythonResponseWithoutVersion() {
        ResponseEntity<JsonNode> response = http.getForEntity("/health/ready", JsonNode.class);
        assertThat(response.getStatusCode().value()).isEqualTo(200);
        assertThat(response.getBody().path("service").asText()).isEqualTo("hotline-java-api");
        assertThat(response.getBody().path("python").path("service").asText()).isEqualTo("hotline-agent");
        assertThat(response.getBody().path("python").path("version").asText()).isEmpty();
    }

    @Test
    void livenessRemainsAvailableWhenPythonIsUnavailable() {
        healthStatus = 503;
        readinessStatus = 503;
        assertThat(http.getForEntity("/health/live", JsonNode.class).getStatusCode().value()).isEqualTo(200);
        assertThat(http.getForEntity("/health/ready", JsonNode.class).getStatusCode().value()).isEqualTo(503);
    }

    @Test
    void discoveryAndRegistrationHaveIndependentSwitches() {
        assertThat(environment.getProperty("HOTLINE_NACOS_ENABLED", Boolean.class)).isTrue();
        assertThat(environment.getProperty("spring.cloud.nacos.discovery.register-enabled", Boolean.class)).isFalse();
    }

    @Test
    void redirectWithHealthyJsonIsUnavailable() {
        healthStatus = 302;
        ResponseEntity<JsonNode> response = http.getForEntity("/api/v1/capabilities/python/health", JsonNode.class);
        assertThat(response.getStatusCode().value()).isEqualTo(503);
        assertThat(response.getBody().path("code").asText()).isEqualTo("PYTHON_UNAVAILABLE");
    }

    @Test
    void upstreamFailureReturnsASafeError() {
        healthStatus = 500;
        healthBody = "{\"detail\":\"private diagnostic\"}";
        ResponseEntity<String> response = http.getForEntity("/api/v1/capabilities/python/health", String.class);
        assertThat(response.getStatusCode().value()).isEqualTo(503);
        assertThat(response.getBody()).contains("PYTHON_UNAVAILABLE")
                .doesNotContain("private diagnostic", "127.0.0.1", "http://");
    }

    @Test
    void malformedAndIncompleteResponsesAreUnavailable() {
        healthBody = "invalid-json";
        assertThat(http.getForEntity("/api/v1/capabilities/python/health", String.class)
                .getStatusCode().value()).isEqualTo(503);
        healthBody = "{\"status\":\"UP\"}";
        assertThat(http.getForEntity("/api/v1/capabilities/python/health", String.class)
                .getStatusCode().value()).isEqualTo(503);
    }
}
