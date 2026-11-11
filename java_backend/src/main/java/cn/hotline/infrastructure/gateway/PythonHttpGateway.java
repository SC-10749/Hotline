package cn.hotline.infrastructure.gateway;

import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import cn.hotline.infrastructure.config.PythonServiceProperties;
import cn.hotline.domain.capability.PythonUnavailableException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;

/** Streams capability protocols without buffering uploads, downloads or SSE. */
@Component
public class PythonHttpGateway {
    private static final Set<String> HOP_HEADERS = Set.of("connection", "keep-alive", "proxy-authenticate",
            "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade", "host", "content-length");
    private static final Set<String> REQUEST_HEADERS = Set.of("accept", "content-type", "authorization",
            "last-event-id", "range", "if-none-match", "if-modified-since", "x-request-id");
    private final HttpClient client;
    private final PythonEndpointResolver endpoints;
    private final PythonServiceProperties properties;

    public PythonHttpGateway(HttpClient pythonHttpClient, PythonEndpointResolver endpoints,
                             PythonServiceProperties properties) {
        this.client = pythonHttpClient;
        this.endpoints = endpoints;
        this.properties = properties;
    }

    public void forward(HttpServletRequest request, HttpServletResponse response) throws IOException {
        String path = request.getRequestURI();
        // Never allow a request path to replace the configured upstream authority.
        if (!path.startsWith("/") || path.startsWith("//") || path.contains("\\")) {
            response.sendError(400);
            return;
        }
        URI target = endpoints.resolve(path + (request.getQueryString() == null ? "" : "?" + request.getQueryString()));
        HttpRequest.Builder outgoing = HttpRequest.newBuilder(target).timeout(properties.readTimeout());
        for (String name : REQUEST_HEADERS) {
            var values = request.getHeaders(name);
            while (values.hasMoreElements()) outgoing.header(name, values.nextElement());
        }
        var body = request.getContentLengthLong() == 0 || Set.of("GET", "HEAD").contains(request.getMethod())
                ? HttpRequest.BodyPublishers.noBody()
                : HttpRequest.BodyPublishers.ofInputStream(() -> {
                    try { return request.getInputStream(); }
                    catch (IOException exception) { throw new java.io.UncheckedIOException(exception); }
                });
        outgoing.method(request.getMethod(), body);
        HttpResponse<InputStream> upstream;
        try {
            upstream = client.send(outgoing.build(), HttpResponse.BodyHandlers.ofInputStream());
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new PythonUnavailableException();
        } catch (IOException exception) {
            throw new PythonUnavailableException();
        }
        try (InputStream input = upstream.body()) {
            response.setStatus(upstream.statusCode());
            Set<String> excluded = new HashSet<>(HOP_HEADERS);
            upstream.headers().allValues("connection").forEach(value -> {
                for (String token : value.split(",")) excluded.add(token.trim().toLowerCase(Locale.ROOT));
            });
            upstream.headers().map().forEach((name, values) -> {
                if (!excluded.contains(name.toLowerCase(Locale.ROOT))) {
                    values.forEach(value -> response.addHeader(name, value));
                }
            });
            boolean stream = upstream.headers().firstValue("content-type").orElse("").startsWith("text/event-stream");
            if (stream) response.setHeader("X-Accel-Buffering", "no");
            // Commit upstream headers before waiting for the first event.
            response.flushBuffer();
            byte[] buffer = new byte[16384];
            int count;
            while ((count = input.read(buffer)) != -1) {
                response.getOutputStream().write(buffer, 0, count);
                if (stream) response.flushBuffer();
            }
        }
        // A disconnected browser closes the upstream stream via try-with-resources.
    }
}
