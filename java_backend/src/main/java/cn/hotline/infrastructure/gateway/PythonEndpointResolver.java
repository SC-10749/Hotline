package cn.hotline.infrastructure.gateway;

import java.net.URI;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import cn.hotline.domain.capability.PythonUnavailableException;
import cn.hotline.infrastructure.config.PythonServiceProperties;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
public class PythonEndpointResolver {
    private final PythonServiceProperties properties;
    private final ObjectProvider<DiscoveryClient> discovery;
    private final AtomicInteger sequence = new AtomicInteger();

    public PythonEndpointResolver(PythonServiceProperties properties, ObjectProvider<DiscoveryClient> discovery) {
        this.properties = properties;
        this.discovery = discovery;
    }

    public URI resolve(String path) {
        if (properties.mode() == PythonServiceProperties.Mode.STATIC) {
            return properties.baseUrl().resolve(path);
        }
        try {
            DiscoveryClient client = discovery.getIfAvailable();
            if (client == null) {
                throw new PythonUnavailableException();
            }
            List<ServiceInstance> instances = client.getInstances(properties.serviceName()).stream()
                    .filter(instance -> "1".equals(instance.getMetadata().get("apiVersion")))
                    .filter(instance -> !Boolean.parseBoolean(instance.getMetadata().get("draining")))
                    .filter(instance -> PythonServiceProperties.isHttpOrigin(instance.getUri()))
                    .toList();
            if (instances.isEmpty()) {
                throw new PythonUnavailableException();
            }
            int index = Math.floorMod(sequence.getAndIncrement(), instances.size());
            return instances.get(index).getUri().resolve(path);
        } catch (RuntimeException exception) {
            // Discovery diagnostics may contain private connection details.
            throw new PythonUnavailableException();
        }
    }
}
