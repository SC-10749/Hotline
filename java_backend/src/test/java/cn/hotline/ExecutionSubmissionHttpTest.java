package cn.hotline;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {"spring.cloud.nacos.discovery.enabled=false", "hotline.python.mode=static",
                "hotline.admission.store=memory", "hotline.admission.submission-quota-per-day=1"})
class ExecutionSubmissionHttpTest {

    private static final HttpServer UPSTREAM = upstream();
    private static volatile int runStatus;
    private static volatile String lastRequestBody;

    @Autowired
    private TestRestTemplate http;

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("hotline.python.base-url", () -> "http://127.0.0.1:" + UPSTREAM.getAddress().getPort());
    }

    private static HttpServer upstream() {
        try {
            HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/execution/runs", exchange -> {
                lastRequestBody = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
                String body = runStatus == 200
                        ? "{\"run\":{\"run_id\":\"run-123\",\"status\":\"queued\"}}"
                        : "{\"detail\":\"rejected\"}";
                byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set("Content-Type", "application/json");
                exchange.sendResponseHeaders(runStatus, bytes.length);
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
        runStatus = 200;
    }

    @AfterAll
    static void stop() {
        UPSTREAM.stop(0);
    }

    @Test
    void acceptsValidSubmissionAndReturnsRunReference() throws IOException {
        ResponseEntity<JsonNode> response = post("submit-ok",
                "{\"conversationId\":\"conv-1\",\"agent\":\"chat\",\"query\":\"hello\"}");

        assertThat(response.getStatusCode().value()).isEqualTo(202);
        JsonNode body = response.getBody();
        assertThat(body.path("requestId").asText()).isNotBlank();
        assertThat(body.path("runId").asText()).isEqualTo("run-123");
        assertThat(body.path("status").asText()).isEqualTo("queued");

        JsonNode forwarded = new ObjectMapper().readTree(lastRequestBody);
        assertThat(forwarded.path("conversationId").asText()).isEqualTo("conv-1");
        assertThat(forwarded.path("agent").asText()).isEqualTo("chat");
        assertThat(forwarded.path("query").asText()).isEqualTo("hello");
    }

    @Test
    void mapsCapacityFailureTo503() {
        runStatus = 503;

        ResponseEntity<JsonNode> response = post("capacity-1", "{\"conversationId\":\"conv-2\",\"query\":\"hello\"}");

        assertThat(response.getStatusCode().value()).isEqualTo(503);
        assertThat(response.getBody().path("code").asText()).isEqualTo("CAPACITY_UNAVAILABLE");
    }

    @Test
    void mapsActiveExecutionConflictTo409() {
        runStatus = 409;

        ResponseEntity<JsonNode> response = post("conflict-1", "{\"conversationId\":\"conv-3\",\"query\":\"hello\"}");

        assertThat(response.getStatusCode().value()).isEqualTo(409);
        assertThat(response.getBody().path("code").asText()).isEqualTo("INVALID_STATE");
    }

    @Test
    void dailyQuotaDeniesFurtherSubmissions() {
        assertThat(post("quota-1", "{\"conversationId\":\"conv-4\",\"query\":\"hello\"}")
                .getStatusCode().value()).isEqualTo(202);

        ResponseEntity<JsonNode> denied = post("quota-1", "{\"conversationId\":\"conv-4\",\"query\":\"hello\"}");

        assertThat(denied.getStatusCode().value()).isEqualTo(429);
        assertThat(denied.getBody().path("code").asText()).isEqualTo("QUOTA_EXCEEDED");
    }

    @Test
    void rejectsMissingQueryWith400() {
        ResponseEntity<JsonNode> response = post("invalid-1", "{\"conversationId\":\"conv-5\"}");

        assertThat(response.getStatusCode().value()).isEqualTo(400);
        assertThat(response.getBody().path("code").asText()).isEqualTo("INVALID_ARGUMENT");
    }

    private ResponseEntity<JsonNode> post(String user, String json) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.set("X-Hotline-User", user);
        return http.exchange("/api/v1/execution/requests", HttpMethod.POST,
                new HttpEntity<>(json, headers), JsonNode.class);
    }
}
