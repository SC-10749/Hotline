package cn.hotline.infrastructure.config;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

import java.time.Duration;
import java.util.List;

/** 接入治理配置（hotline.admission.*）：黑名单、限流、并发与提交配额。 */
@Validated
@ConfigurationProperties("hotline.admission")
public record AdmissionProperties(
        boolean enabled,
        @NotNull Store store,
        boolean redisFailOpen,
        @NotBlank String clientHeader,
        @Min(1) int maxClientHeaderLength,
        boolean trustForwardedFor,
        @NotNull RateLimit rateLimit,
        @NotNull Concurrency concurrency,
        @Min(0) long submissionQuotaPerDay,
        @NotNull List<String> includePaths,
        @NotNull List<String> concurrencyPaths) {

    /** 存储选择：auto 启动时探测 Redis，不可用回退内存并告警。 */
    public enum Store {
        AUTO, MEMORY, REDIS
    }

    /** 固定窗口限流。 */
    public record RateLimit(@Min(1) int limit, @NotNull Duration window) {
    }

    /** 并发租约。 */
    public record Concurrency(@Min(1) int limit, @NotNull Duration lease) {
    }
}
