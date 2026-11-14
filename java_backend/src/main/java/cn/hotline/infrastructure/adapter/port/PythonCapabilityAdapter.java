package cn.hotline.infrastructure.adapter.port;

import cn.hotline.domain.capability.PythonCapabilityPort;
import cn.hotline.domain.capability.PythonHealth;
import cn.hotline.domain.capability.PythonUnavailableException;
import cn.hotline.domain.execution.ExecutionCapacityUnavailableException;
import cn.hotline.domain.execution.ExecutionConflictException;
import cn.hotline.domain.execution.ExecutionInvalidArgumentException;
import cn.hotline.domain.execution.ExecutionRun;
import cn.hotline.domain.execution.ExecutionSubmission;
import cn.hotline.domain.execution.ExecutionTargetNotFoundException;
import cn.hotline.infrastructure.gateway.PythonEndpointResolver;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import java.util.LinkedHashMap;
import java.util.Map;

@Component
public class PythonCapabilityAdapter implements PythonCapabilityPort {

    private static final ParameterizedTypeReference<Map<String, Object>> MAP_TYPE =
            new ParameterizedTypeReference<>() {
            };

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

    @Override
    public Map<String, Object> skillCatalog() {
        try {
            Map<String, Object> envelope = client.get()
                    .uri(endpoints.resolve("/skill/list"))
                    .retrieve()
                    .onStatus(status -> !status.is2xxSuccessful(), (request, result) -> {
                        throw new PythonUnavailableException();
                    })
                    .body(MAP_TYPE);
            Object data = envelope == null ? null : envelope.get("data");
            if (!(data instanceof Map<?, ?> catalog)) {
                throw new PythonUnavailableException();
            }
            return toStringKeyMap(catalog);
        } catch (RestClientException exception) {
            throw new PythonUnavailableException();
        }
    }

    @Override
    public Map<String, Object> harnessOverview() {
        try {
            Map<String, Object> overview = client.get()
                    .uri(endpoints.resolve("/harness/overview"))
                    .retrieve()
                    .onStatus(status -> !status.is2xxSuccessful(), (request, result) -> {
                        throw new PythonUnavailableException();
                    })
                    .body(MAP_TYPE);
            if (overview == null) {
                throw new PythonUnavailableException();
            }
            return overview;
        } catch (RestClientException exception) {
            throw new PythonUnavailableException();
        }
    }

    @Override
    public ExecutionRun createExecutionRun(ExecutionSubmission submission) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("conversationId", submission.conversationId());
        payload.put("agent", submission.agent());
        payload.put("query", submission.query());
        if (submission.fileId() != null) {
            payload.put("fileId", submission.fileId());
        }
        if (submission.agentId() != null) {
            payload.put("agentId", submission.agentId());
        }
        if (submission.workspaceId() != null) {
            payload.put("workspaceId", submission.workspaceId());
        }
        try {
            Map<String, Object> response = client.post()
                    .uri(endpoints.resolve("/execution/runs"))
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(payload)
                    .retrieve()
                    .onStatus(status -> !status.is2xxSuccessful(), (request, result) -> {
                        throw mapExecutionError(result.getStatusCode());
                    })
                    .body(MAP_TYPE);
            Object run = response == null ? null : response.get("run");
            if (!(run instanceof Map<?, ?> runView)) {
                throw new PythonUnavailableException();
            }
            Object runId = runView.get("run_id");
            if (runId == null || String.valueOf(runId).isBlank()) {
                throw new PythonUnavailableException();
            }
            Object status = runView.get("status");
            return new ExecutionRun(String.valueOf(runId), status == null ? "unknown" : String.valueOf(status));
        } catch (RestClientException exception) {
            throw new PythonUnavailableException();
        }
    }

    private PythonHealth request(String path) {
        try {
            PythonHealthResponse response = client.get()
                    .uri(endpoints.resolve(path))
                    .retrieve()
                    .onStatus(status -> !status.is2xxSuccessful(), (request, result) -> {
                        throw new PythonUnavailableException();
                    })
                    .body(PythonHealthResponse.class);
            if (response == null || !"UP".equals(response.status())
                    || response.service() == null || response.service().isBlank()) {
                throw new PythonUnavailableException();
            }
            return new PythonHealth(response.status(), response.service(),
                    response.version() == null ? "" : response.version());
        } catch (RestClientException exception) {
            throw new PythonUnavailableException();
        }
    }

    /** 将 Python 的错误状态映射为类型化异常，交由统一错误契约处理。 */
    private RuntimeException mapExecutionError(HttpStatusCode statusCode) {
        int value = statusCode.value();
        if (value == 404) {
            return new ExecutionTargetNotFoundException("执行目标不存在");
        }
        if (value == 409) {
            return new ExecutionConflictException("目标当前状态不允许提交");
        }
        if (value == 400 || value == 415 || value == 422) {
            return new ExecutionInvalidArgumentException("执行提交参数不合法");
        }
        if (value == 503 || statusCode.is5xxServerError()) {
            return new ExecutionCapacityUnavailableException("执行服务容量不足，请稍后重试");
        }
        return new ExecutionInvalidArgumentException("执行提交被拒绝");
    }

    private static Map<String, Object> toStringKeyMap(Map<?, ?> source) {
        Map<String, Object> result = new LinkedHashMap<>();
        source.forEach((key, value) -> result.put(String.valueOf(key), value));
        return result;
    }

    private record PythonHealthResponse(String status, String service, String version) {
    }
}
