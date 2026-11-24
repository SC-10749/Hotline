package cn.hotline.infrastructure.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/** Shared secret between the Java entry point and the Python capability API. */
@ConfigurationProperties("hotline.security")
public record SecurityProperties(String token) {

    public SecurityProperties {
        token = token == null ? "" : token.trim();
    }
}
