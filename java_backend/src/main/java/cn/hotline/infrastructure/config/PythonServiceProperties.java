package cn.hotline.infrastructure.config;

import java.net.URI;
import java.time.Duration;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties("hotline.python")
public record PythonServiceProperties(
        @NotNull Mode mode,
        @NotNull URI baseUrl,
        @NotBlank String serviceName,
        @NotNull Duration connectTimeout,
        @NotNull Duration readTimeout) {

    public enum Mode { STATIC, NACOS }

    public PythonServiceProperties {
        if (baseUrl != null && !isHttpOrigin(baseUrl)) {
            throw new IllegalArgumentException("Python base URL must be an HTTP(S) origin");
        }
        if (connectTimeout != null && !connectTimeout.isPositive()) {
            throw new IllegalArgumentException("Python connect timeout must be positive");
        }
        if (readTimeout != null && !readTimeout.isPositive()) {
            throw new IllegalArgumentException("Python read timeout must be positive");
        }
    }

    public static boolean isHttpOrigin(URI uri) {
        return ("http".equals(uri.getScheme()) || "https".equals(uri.getScheme()))
                && uri.getHost() != null
                && uri.getRawUserInfo() == null
                && uri.getRawQuery() == null
                && uri.getRawFragment() == null
                && (uri.getRawPath().isEmpty() || "/".equals(uri.getRawPath()))
                && (uri.getPort() == -1 || uri.getPort() > 0 && uri.getPort() <= 65535);
    }
}
