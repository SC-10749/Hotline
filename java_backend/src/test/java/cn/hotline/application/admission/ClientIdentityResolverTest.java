package cn.hotline.application.admission;

import cn.hotline.infrastructure.config.AdmissionProperties;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class ClientIdentityResolverTest {

    private final ClientIdentityResolver resolver = new ClientIdentityResolver(properties(false));
    private final ClientIdentityResolver trustingResolver = new ClientIdentityResolver(properties(true));

    @Test
    void headerTakesPrecedenceOverRemoteAddress() {
        assertThat(resolver.resolve("10.0.0.8", "alice", null)).isEqualTo("user:alice");
        assertThat(resolver.resolve("10.0.0.8", "  alice  ", null)).isEqualTo("user:alice");
    }

    @Test
    void invalidHeaderFallsBackToRemoteAddress() {
        assertThat(resolver.resolve("10.0.0.8", "   ", null)).isEqualTo("ip:10.0.0.8");
        assertThat(resolver.resolve("10.0.0.8", "bad" + (char) 1 + "value", null)).isEqualTo("ip:10.0.0.8");
        assertThat(resolver.resolve("10.0.0.8", "x".repeat(129), null)).isEqualTo("ip:10.0.0.8");
    }

    @Test
    void forwardedForIsOnlyTrustedWhenConfigured() {
        assertThat(resolver.resolve("10.0.0.8", null, "1.2.3.4, 5.6.7.8")).isEqualTo("ip:10.0.0.8");
        assertThat(trustingResolver.resolve("10.0.0.8", null, "1.2.3.4, 5.6.7.8")).isEqualTo("ip:1.2.3.4");
    }

    @Test
    void missingRemoteAddressYieldsUnknown() {
        assertThat(resolver.resolve(null, null, null)).isEqualTo("ip:unknown");
    }

    private static AdmissionProperties properties(boolean trustForwardedFor) {
        return new AdmissionProperties(true, AdmissionProperties.Store.MEMORY, false, "X-Hotline-User", 128,
                trustForwardedFor, new AdmissionProperties.RateLimit(600, Duration.ofMinutes(1)),
                new AdmissionProperties.Concurrency(4, Duration.ofMinutes(30)), 0L,
                List.of("/api/**"), List.of("/execution/**"));
    }
}
