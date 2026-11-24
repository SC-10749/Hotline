package cn.hotline;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {"spring.cloud.nacos.discovery.enabled=false", "hotline.python.mode=static",
                "hotline.admission.store=memory",
                "hotline.admission.rate-limit.limit=2", "hotline.admission.rate-limit.window=2s"})
class AdmissionRateLimitHttpTest {

    private static final HttpServer UPSTREAM = upstream();

    @LocalServerPort
    int port;

    // TestRestTemplate 底层的 Apache HttpClient 会按 Retry-After 自动重试 429，这里用不重试的 JDK 客户端观察真实响应。
    private final HttpClient http = HttpClient.newHttpClient();

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
    void rateLimitReturns429WithRetryAfterAndRecoversAfterWindow() throws Exception {
        assertThat(getWithUser("limited-1").statusCode()).isEqualTo(200);
        assertThat(getWithUser("limited-1").statusCode()).isEqualTo(200);

        HttpResponse<String> denied = getWithUser("limited-1");
        assertThat(denied.statusCode()).isEqualTo(429);
        assertThat(denied.body()).contains("QUOTA_EXCEEDED");
        long retryAfter = Long.parseLong(denied.headers().firstValue("Retry-After").orElseThrow());
        assertThat(retryAfter).isBetween(1L, 2L);

        // 其他调用方不受该调用方窗口影响
        assertThat(getWithUser("limited-2").statusCode()).isEqualTo(200);

        Thread.sleep(retryAfter * 1000 + 200);

        assertThat(getWithUser("limited-1").statusCode()).isEqualTo(200);
    }

    private HttpResponse<String> getWithUser(String user) throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(
                        URI.create("http://127.0.0.1:" + port + "/api/v1/capabilities/python/health"))
                .header("X-Hotline-User", user)
                .build();
        return http.send(request, HttpResponse.BodyHandlers.ofString());
    }
}
