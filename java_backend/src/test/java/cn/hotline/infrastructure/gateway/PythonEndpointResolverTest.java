package cn.hotline.infrastructure.gateway;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import cn.hotline.domain.capability.PythonUnavailableException;
import cn.hotline.infrastructure.config.PythonServiceProperties;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class PythonEndpointResolverTest {
    @Mock
    private ObjectProvider<DiscoveryClient> provider;

    @Mock
    private DiscoveryClient discovery;

    private PythonServiceProperties properties(PythonServiceProperties.Mode mode) {
        return new PythonServiceProperties(mode, URI.create("http://127.0.0.1:8888"),
                "hotline-python-api", Duration.ofSeconds(1), Duration.ofSeconds(3));
    }

    private DefaultServiceInstance instance(String id, int port, String version, boolean draining) {
        DefaultServiceInstance instance = new DefaultServiceInstance(id, "hotline-python-api", "127.0.0.1", port, false);
        instance.getMetadata().put("apiVersion", version);
        instance.getMetadata().put("draining", Boolean.toString(draining));
        return instance;
    }

    @Test
    void staticModeDoesNotContactDiscovery() {
        PythonEndpointResolver resolver = new PythonEndpointResolver(properties(PythonServiceProperties.Mode.STATIC), provider);
        assertThat(resolver.resolve("/health")).isEqualTo(URI.create("http://127.0.0.1:8888/health"));
        verifyNoInteractions(provider);
    }

    @Test
    void discoveryFiltersIncompatibleAndDrainingInstancesAndRotatesCandidates() {
        when(provider.getIfAvailable()).thenReturn(discovery);
        when(discovery.getInstances("hotline-python-api")).thenReturn(List.of(
                instance("old", 9000, "0", false), instance("draining", 9001, "1", true),
                instance("first", 9002, "1", false), instance("second", 9003, "1", false)));
        PythonEndpointResolver resolver = new PythonEndpointResolver(properties(PythonServiceProperties.Mode.NACOS), provider);
        assertThat(resolver.resolve("/health").getPort()).isEqualTo(9002);
        assertThat(resolver.resolve("/health").getPort()).isEqualTo(9003);
        assertThat(resolver.resolve("/health").getPort()).isEqualTo(9002);
    }

    @Test
    void emptyDiscoveryDoesNotFallBackToTheStaticAddress() {
        when(provider.getIfAvailable()).thenReturn(discovery);
        when(discovery.getInstances("hotline-python-api")).thenReturn(List.of());
        PythonEndpointResolver resolver = new PythonEndpointResolver(properties(PythonServiceProperties.Mode.NACOS), provider);
        assertThatThrownBy(() -> resolver.resolve("/health")).isInstanceOf(PythonUnavailableException.class);
    }

    @Test
    void rejectsInvalidOriginsAndTimeouts() {
        assertThatThrownBy(() -> new PythonServiceProperties(PythonServiceProperties.Mode.STATIC,
                URI.create("http://user:password@127.0.0.1/"), "python", Duration.ofSeconds(1), Duration.ofSeconds(3)))
                .isInstanceOf(IllegalArgumentException.class).hasMessageNotContaining("password");
        assertThatThrownBy(() -> new PythonServiceProperties(PythonServiceProperties.Mode.STATIC,
                URI.create("http://127.0.0.1/"), "python", Duration.ZERO, Duration.ofSeconds(3)))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
