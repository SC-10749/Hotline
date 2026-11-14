package cn.hotline.infrastructure.config;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

import java.time.Duration;

/** 流程编排配置（hotline.flow.*）。 */
@Validated
@ConfigurationProperties("hotline.flow")
public record FlowProperties(
        @NotBlank String scenesLocation,
        @NotBlank String funcmapsLocation,
        @NotNull Pool pool) {

    /** 并行任务线程池参数。 */
    public record Pool(@Min(1) int coreSize, @Min(1) int maxSize, @NotNull Duration keepAlive) {

        public Pool {
            if (maxSize < coreSize) {
                throw new IllegalArgumentException("hotline.flow.pool.max-size 不能小于 core-size");
            }
        }
    }
}
