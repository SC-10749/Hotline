package cn.hotline.application.admission;

import cn.hotline.domain.admission.AdmissionStore;
import cn.hotline.domain.admission.AdmissionStoreUnavailableException;
import cn.hotline.infrastructure.admission.InMemoryAdmissionStore;
import cn.hotline.infrastructure.config.AdmissionProperties;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class AdmissionServiceTest {

    private final InMemoryAdmissionStore store = new InMemoryAdmissionStore();
    private final AdmissionService service = new AdmissionService(store, properties(false, 2, 1));

    @Test
    void blacklistedClientIsDeniedFirst() {
        store.addToBlacklist("user:bad");

        AdmissionService.Decision decision = service.check("user:bad", "/api/v1/capabilities/overview");

        assertThat(decision.allowed()).isFalse();
        assertThat(decision.reason()).isEqualTo(AdmissionService.DenyReason.BLACKLIST);
    }

    @Test
    void rateLimitDeniesBeyondLimitAndSuggestsRetry() {
        assertThat(service.check("user:a", "/api/v1/capabilities/overview").allowed()).isTrue();
        assertThat(service.check("user:a", "/api/v1/capabilities/overview").allowed()).isTrue();

        AdmissionService.Decision denied = service.check("user:a", "/api/v1/capabilities/overview");

        assertThat(denied.allowed()).isFalse();
        assertThat(denied.reason()).isEqualTo(AdmissionService.DenyReason.RATE_LIMIT);
        assertThat(denied.retryAfter()).isNotNull().isPositive();
    }

    @Test
    void concurrencyLeaseIsHeldUntilReleased() {
        AdmissionService concurrencyService = new AdmissionService(store, properties(false, 10, 1));

        AdmissionService.Decision first = concurrencyService.check("user:a", "/execution/runs");
        assertThat(first.allowed()).isTrue();
        assertThat(first.leaseKey()).isNotBlank();
        assertThat(first.leaseId()).isNotBlank();

        AdmissionService.Decision second = concurrencyService.check("user:a", "/execution/runs");
        assertThat(second.allowed()).isFalse();
        assertThat(second.reason()).isEqualTo(AdmissionService.DenyReason.CONCURRENCY);

        concurrencyService.release(first);

        assertThat(concurrencyService.check("user:a", "/execution/runs").allowed()).isTrue();
    }

    @Test
    void pathMatchingFollowsIncludeAndConcurrencyPatterns() {
        assertThat(service.included("/api/v1/capabilities/overview")).isTrue();
        assertThat(service.included("/health/ready")).isFalse();
        assertThat(service.included(null)).isFalse();

        // 非并发路径不占用租约
        AdmissionService.Decision decision = service.check("user:a", "/skill/list");
        assertThat(decision.allowed()).isTrue();
        assertThat(decision.leaseKey()).isNull();
    }

    @Test
    void storeFailureFailsClosedByDefault() {
        AdmissionService failClosed = new AdmissionService(failingStore(), properties(false, 10, 1));

        assertThatThrownBy(() -> failClosed.check("user:a", "/api/v1/capabilities/overview"))
                .isInstanceOf(AdmissionStoreUnavailableException.class);
    }

    @Test
    void storeFailureFailsOpenWhenConfigured() {
        AdmissionService failOpen = new AdmissionService(failingStore(), properties(true, 10, 1));

        AdmissionService.Decision decision = failOpen.check("user:a", "/api/v1/capabilities/overview");

        assertThat(decision.allowed()).isTrue();
    }

    private static AdmissionStore failingStore() {
        AdmissionStore failing = mock(AdmissionStore.class);
        when(failing.isBlacklisted(anyString())).thenThrow(new AdmissionStoreUnavailableException("存储不可用"));
        return failing;
    }

    private static AdmissionProperties properties(boolean failOpen, int rateLimit, int concurrencyLimit) {
        return new AdmissionProperties(true, AdmissionProperties.Store.MEMORY, failOpen, "X-Hotline-User", 128, false,
                new AdmissionProperties.RateLimit(rateLimit, Duration.ofMinutes(1)),
                new AdmissionProperties.Concurrency(concurrencyLimit, Duration.ofMinutes(30)),
                0L, List.of("/api/**", "/execution/**", "/skill/**"), List.of("/execution/**"));
    }
}
