package cn.hotline.infrastructure.adapter.port;

import cn.hotline.domain.capability.PythonCapabilityPort;
import cn.hotline.domain.capability.PythonHealth;
import cn.hotline.domain.capability.PythonUnavailableException;
import cn.hotline.infrastructure.gateway.PythonEndpointResolver;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

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

    private record PythonHealthResponse(String status, String service, String version) {
    }
}
