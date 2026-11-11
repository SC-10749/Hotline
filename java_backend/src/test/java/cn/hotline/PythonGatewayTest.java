package cn.hotline;

import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {"spring.cloud.nacos.discovery.enabled=false", "hotline.python.mode=nacos"})
class PythonGatewayTest {
    private static final HttpServer UPSTREAM = upstream();
    private static volatile String receivedBody;
    private static volatile String receivedQuery;
    private static volatile String receivedCursor;
    private static volatile String receivedType;
    @LocalServerPort int port;
    @MockitoBean DiscoveryClient discovery;
    private final HttpClient http = HttpClient.newHttpClient();

    private static HttpServer upstream() {
        try {
            HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.setExecutor(java.util.concurrent.Executors.newVirtualThreadPerTaskExecutor());
            server.createContext("/", exchange -> {
                receivedBody = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
                receivedQuery = exchange.getRequestURI().getRawQuery();
                receivedCursor = exchange.getRequestHeaders().getFirst("Last-Event-ID");
                receivedType = exchange.getRequestHeaders().getFirst("Content-Type");
                if (exchange.getRequestURI().getPath().endsWith("/stream")) {
                    exchange.getResponseHeaders().set("Content-Type", "text/event-stream");
                    exchange.sendResponseHeaders(200, 0);
                    try (var output = exchange.getResponseBody()) {
                        output.write("id: 8\ndata: first\n\n".getBytes(StandardCharsets.UTF_8));
                        output.flush();
                        try { Thread.sleep(1200); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
                        output.write("event: done\ndata: {}\n\n".getBytes(StandardCharsets.UTF_8));
                    }
                } else {
                    exchange.getResponseHeaders().set("Content-Type", "application/json");
                    byte[] body = "{\"run_id\":\"demo\"}".getBytes(StandardCharsets.UTF_8);
                    exchange.sendResponseHeaders(exchange.getRequestURI().getPath().endsWith("/missing") ? 404 : 200, body.length);
                    try (var output = exchange.getResponseBody()) { output.write(body); }
                }
            });
            server.start();
            return server;
        } catch (Exception e) { throw new IllegalStateException(e); }
    }

    @BeforeEach void instances() {
        var instance = new DefaultServiceInstance("python", "hotline-python-api", "127.0.0.1", UPSTREAM.getAddress().getPort(), false);
        instance.getMetadata().put("apiVersion", "1");
        when(discovery.getInstances("hotline-python-api")).thenReturn(List.of(instance));
    }

    private URI uri(String path) { return URI.create("http://127.0.0.1:" + port + path); }

    @Test void discoversPythonAndForwardsSubmissionQueryAndErrors() throws Exception {
        var request = HttpRequest.newBuilder(uri("/execution/runs?source=a%20b"))
                .header("Content-Type", "application/json").POST(HttpRequest.BodyPublishers.ofString("{\"query\":\"hello\"}")).build();
        var response = http.send(request, HttpResponse.BodyHandlers.ofString());
        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.body()).contains("demo");
        assertThat(receivedBody).isEqualTo("{\"query\":\"hello\"}");
        assertThat(receivedQuery).isEqualTo("source=a%20b");
        assertThat(http.send(HttpRequest.newBuilder(uri("/execution/missing")).build(), HttpResponse.BodyHandlers.ofString()).statusCode()).isEqualTo(404);
    }

    @Test void preservesMultipartBytesAndBoundary() throws Exception {
        String payload = "--demo\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.txt\"\r\n\r\nhello\r\n--demo--\r\n";
        var response = http.send(HttpRequest.newBuilder(uri("/file/upload")).header("Content-Type", "multipart/form-data; boundary=demo")
                .POST(HttpRequest.BodyPublishers.ofString(payload)).build(), HttpResponse.BodyHandlers.ofString());
        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(receivedBody).isEqualTo(payload);
        assertThat(receivedType).contains("boundary=demo");
    }

    @Test void streamsFirstEventBeforeCompletionAndForwardsResumeCursor() throws Exception {
        var response = http.send(HttpRequest.newBuilder(uri("/execution/runs/demo/stream"))
                .timeout(Duration.ofSeconds(5)).header("Last-Event-ID", "7").build(), HttpResponse.BodyHandlers.ofInputStream());
        long started = System.nanoTime();
        try (var input = response.body()) {
            assertThat(new String(input.readNBytes(19), StandardCharsets.UTF_8)).isEqualTo("id: 8\ndata: first\n\n");
            assertThat(Duration.ofNanos(System.nanoTime() - started).toMillis()).isLessThan(1000);
            assertThat(new String(input.readAllBytes(), StandardCharsets.UTF_8)).contains("event: done");
        }
        assertThat(receivedCursor).isEqualTo("7");
    }

    @Test void missingInstancesReturnsUnavailable() throws Exception {
        when(discovery.getInstances("hotline-python-api")).thenReturn(List.of());
        var response = http.send(HttpRequest.newBuilder(uri("/skill/list")).build(), HttpResponse.BodyHandlers.ofString());
        assertThat(response.statusCode()).isEqualTo(503);
        assertThat(response.body()).contains("PYTHON_UNAVAILABLE");
    }

    @AfterAll static void stop() { UPSTREAM.stop(0); }
}
