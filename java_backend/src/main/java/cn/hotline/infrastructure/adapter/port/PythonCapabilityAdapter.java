package cn.hotline.infrastructure.adapter.port;

import cn.hotline.domain.capability.PythonCapabilityPort;
import cn.hotline.domain.capability.PythonHealth;
import cn.hotline.domain.capability.PythonUnavailableException;
import cn.hotline.infrastructure.gateway.PythonEndpointResolver;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.ResourceAccessException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.util.ArrayList;

@Component
public class PythonCapabilityAdapter implements PythonCapabilityPort {
    private final RestClient client;
    private final PythonEndpointResolver endpoints;

    public PythonCapabilityAdapter(RestClient pythonRestClient, PythonEndpointResolver endpoints) {
        this.client = pythonRestClient;
        this.endpoints = endpoints;
    }

    @Override
    public PythonHealth health() {
        return request("/health");
    }

    @Override
    public PythonHealth readiness() {
        return request("/health/ready");
    }

    private PythonHealth request(String path) {
        try {
            PythonHealthResponse response = client.get()
                    .uri(endpoints.resolve(path))
                    .retrieve()
                    .onStatus(status -> !status.is2xxSuccessful(), (request, result) -> {
                        String diagnostic = "Python 健康检查返回 HTTP " + result.getStatusCode().value();
                        // Only expose known health flags; upstream bodies may contain secrets.
                        if ("/health/ready".equals(path)) {
                            try {
                                var body = new ObjectMapper().readTree(result.getBody());
                                var failures = new ArrayList<String>();
                                if (body != null && "unavailable".equals(body.path("executionWorker").asText())) {
                                    failures.add("执行 Worker 未运行或心跳过期");
                                }
                                if (body != null && "unavailable".equals(body.path("serviceRegistry").asText())) {
                                    failures.add("Python 服务注册不可用");
                                }
                                if (!failures.isEmpty()) diagnostic += "：" + String.join("；", failures);
                            } catch (java.io.IOException ignored) {
                                // Keep the HTTP diagnostic when the body is not valid health JSON.
                            }
                        }
                        throw new PythonUnavailableException(diagnostic);
                    })
                    .body(PythonHealthResponse.class);
            if (response == null || !"UP".equals(response.status())
                    || response.service() == null || response.service().isBlank()) {
                throw new PythonUnavailableException("Python 健康检查响应缺少有效的 status=UP 或 service 字段");
            }
            return new PythonHealth(response.status(), response.service(),
                    response.version() == null ? "" : response.version());
        } catch (ResourceAccessException exception) {
            for (Throwable cause = exception; cause != null; cause = cause.getCause()) {
                if (cause instanceof ConnectException) {
                    throw new PythonUnavailableException("无法连接 Python 能力服务（连接被拒绝），请确认 Python 网关已启动且 Java 配置的目标端口正确");
                }
                if (cause instanceof SocketTimeoutException || cause instanceof java.net.http.HttpTimeoutException) {
                    throw new PythonUnavailableException("连接或等待 Python 能力服务响应超时");
                }
            }
            throw new PythonUnavailableException("Python 能力服务网络请求失败，请检查连接和 TLS 配置");
        } catch (RestClientException exception) {
            throw new PythonUnavailableException("Python 健康检查响应无法解析为有效 JSON");
        }
    }

    private record PythonHealthResponse(String status, String service, String version) {
    }
}
