package cn.hotline.application.admission;

import cn.hotline.domain.admission.AdmissionStore;
import cn.hotline.domain.admission.AdmissionStoreUnavailableException;
import cn.hotline.infrastructure.config.AdmissionProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.AntPathMatcher;

import java.time.Duration;
import java.util.List;
import java.util.Optional;

/**
 * 接入治理决策：黑名单 → 请求速率 → 并发租约，三级依次检查；
 * 限流计数与并发租约都保存在共享存储（Redis 或内存），因此多实例部署时
 * 额度是全局的。存储故障时按 hotline.admission.redis-fail-open 决定
 * 放行（fail-open）或直接抛出（fail-closed，由过滤器映射为 503）。
 */
@Service
public class AdmissionService {

    private static final Logger log = LoggerFactory.getLogger(AdmissionService.class);
    private static final String RATE_KEY_PREFIX = "hotline:admission:rate:";
    private static final String LEASE_KEY_PREFIX = "hotline:admission:concurrency:";

    private final AdmissionStore admissionStore;
    private final AdmissionProperties properties;
    private final AntPathMatcher pathMatcher = new AntPathMatcher();

    public AdmissionService(AdmissionStore admissionStore, AdmissionProperties properties) {
        this.admissionStore = admissionStore;
        this.properties = properties;
    }

    /** 路径是否纳入治理范围（include-paths 通配匹配）。 */
    public boolean included(String path) {
        return matches(properties.includePaths(), path);
    }

    /** 对请求做治理决策；并发租约在放行时随 Decision 带出，由调用方在请求完成后释放。 */
    public Decision check(String clientKey, String path) {
        try {
            if (admissionStore.isBlacklisted(clientKey)) {
                return Decision.denied(DenyReason.BLACKLIST, null, null, null);
            }
            AdmissionStore.RateCount rateCount = admissionStore.incrementWindow(
                    RATE_KEY_PREFIX + clientKey, properties.rateLimit().window());
            if (rateCount.count() > properties.rateLimit().limit()) {
                return Decision.denied(DenyReason.RATE_LIMIT, rateCount.retryAfter(), null, null);
            }
            if (matches(properties.concurrencyPaths(), path)) {
                String leaseKey = LEASE_KEY_PREFIX + clientKey;
                Optional<String> leaseId = admissionStore.acquireLease(
                        leaseKey, properties.concurrency().limit(), properties.concurrency().lease(), clientKey);
                if (leaseId.isEmpty()) {
                    return Decision.denied(DenyReason.CONCURRENCY, properties.concurrency().lease(), null, null);
                }
                return Decision.allowed(leaseKey, leaseId.get());
            }
            return Decision.allowed(null, null);
        } catch (AdmissionStoreUnavailableException exception) {
            if (properties.redisFailOpen()) {
                log.warn("接入治理存储不可用，按 fail-open 放行：{}", exception.getMessage());
                return Decision.allowed(null, null);
            }
            throw exception;
        }
    }

    /** 请求结束后释放并发租约（尽力而为，失败仅告警——租约会随 lease 超时自动过期）。 */
    public void release(Decision decision) {
        if (decision == null || decision.leaseKey() == null || decision.leaseId() == null) {
            return;
        }
        try {
            admissionStore.releaseLease(decision.leaseKey(), decision.leaseId());
        } catch (AdmissionStoreUnavailableException exception) {
            log.warn("释放并发租约失败：{}", exception.getMessage());
        }
    }

    /** 放行/拒绝的原因分类，供过滤器映射到 HTTP 状态码与错误码。 */
    public enum DenyReason {
        BLACKLIST,
        RATE_LIMIT,
        CONCURRENCY
    }

    /** 治理决策；放行且占用并发租约时携带租约键与租约 ID。 */
    public record Decision(boolean allowed, DenyReason reason, Duration retryAfter, String leaseKey, String leaseId) {

        static Decision allowed(String leaseKey, String leaseId) {
            return new Decision(true, null, null, leaseKey, leaseId);
        }

        static Decision denied(DenyReason reason, Duration retryAfter, String leaseKey, String leaseId) {
            return new Decision(false, reason, retryAfter, leaseKey, leaseId);
        }
    }

    private boolean matches(List<String> patterns, String path) {
        if (path == null || path.isEmpty()) {
            return false;
        }
        for (String pattern : patterns) {
            if (pathMatcher.match(pattern, path)) {
                return true;
            }
        }
        return false;
    }
}
